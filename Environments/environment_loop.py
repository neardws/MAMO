"""A simple agent-environment training loop."""

import operator
import time
from typing import Optional, Sequence
from Environments import base
from acme.utils import counting
from acme.utils import loggers
from acme.utils import observers as observers_lib
from acme.utils import signals
from dm_env import specs
import numpy as np
import tree
from Utilities.FileOperator import save_obj, init_file_name

class EnvironmentLoop(base.Worker):
    """A simple RL environment loop.

    This takes `Environment` and `Actor` instances and coordinates their
    interaction. Agent is updated if `should_update=True`. This can be used as:

        loop = EnvironmentLoop(environment, actor)
        loop.run(num_episodes)

    A `Counter` instance can optionally be given in order to maintain counts
    between different Acme components. If not given a local Counter will be
    created to maintain counts between calls to the `run` method.

    A `Logger` instance can also be passed in order to control the output of the
    loop. If not given a platform-specific default logger will be used as defined
    by utils.loggers.make_default_logger. A string `label` can be passed to easily
    change the label associated with the default logger; this is ignored if a
    `Logger` instance is given.

    A list of 'Observer' instances can be specified to generate additional metrics
    to be logged by the logger. They have access to the 'Environment' instance,
    the current timestep datastruct and the current action.
    """

    def __init__(
        self,
        environment,
        actor: base.Actor,
        counter: Optional[counting.Counter] = None,
        logger: Optional[loggers.Logger] = None,
        should_update: bool = True,
        label: str = 'environment_loop',
        observers: Sequence[observers_lib.EnvLoopObserver] = (),
    ):
        # Internalize agent and environment.
        self._environment = environment
        self._actor = actor
        self._label = label
        self._counter = counter or counting.Counter()
        self._logger = logger or loggers.make_default_logger(label)
        self._should_update = should_update
        self._observers = observers

    def run_episode(self) -> loggers.LoggingData:
        """Run one episode.

        Each episode is a loop which interacts first with the environment to get an
        observation and then give that observation to the agent in order to retrieve
        an action.

        Returns:
        An instance of `loggers.LoggingData`.
        """
        # Reset any counts and start the environment.
        start_time = time.time()
        episode_steps = 0

        # For evaluation, this keeps track of the total undiscounted reward
        # accumulated during the episode.
        episode_return = tree.map_structure(_generate_zeros_from_spec,
                                            self._environment.reward_spec())
        timestep = self._environment.reset()

        # Make the first observation.
        self._actor.observe_first(timestep)
        for observer in self._observers:
            # Initialize the observer with the current state of the env after reset
            # and the initial timestep.
            observer.observe_first(self._environment, timestep)

        cumulative_aovs: float = 0
        cumulative_costs: float = 0
        average_aovs: float = 0
        average_costs: float = 0
        average_timelinesss: float = 0
        average_consistencys: float = 0
        average_redundancys: float = 0
        average_sensing_costs: float = 0
        average_transmission_costs: float = 0         
        
        # Run an episode.
        while not timestep.last():
            # Generate an action from the agent's policy and step the environment.
            action = self._actor.select_action(timestep.observation, timestep.vehicle_observation)
            timestep, cumulative_aov, cumulative_cost, average_aov, average_cost, average_timeliness, average_consistency, average_redundancy, average_sensing_cost, average_transmission_cost = self._environment.step(action)
            
            cumulative_aovs += cumulative_aov
            cumulative_costs += cumulative_cost
            average_aovs += average_aov
            average_costs += average_cost
            average_timelinesss += average_timeliness
            average_consistencys += average_consistency
            average_redundancys += average_redundancy
            average_sensing_costs += average_sensing_cost
            average_transmission_costs += average_transmission_cost
            
            # Have the agent observe the timestep and let the actor update itself.
            self._actor.observe(action=action, next_timestep=timestep)
            for observer in self._observers:
                # One environment step was completed. Observe the current state of the
                # environment, the current timestep and the action.
                observer.observe(self._environment, timestep, action)
            if self._should_update:
                self._actor.update()
            # Book-keeping.
            episode_steps += 1
            # Equivalent to: episode_return += timestep.reward
            # We capture the return value because if timestep.reward is a JAX
            # DeviceArray, episode_return will not be mutated in-place. (In all other
            # cases, the returned episode_return will be the same object as the
            # argument episode_return.)
            episode_return = tree.map_structure(operator.iadd,
                                                episode_return,
                                                timestep.reward)

        # Record counts.
        counts = self._counter.increment(episodes=1, steps=episode_steps)

        # Collect the results and combine with counts.
        steps_per_second = episode_steps / (time.time() - start_time)
        average_aovs /= episode_steps
        average_costs /= episode_steps
        average_timelinesss /= episode_steps
        average_consistencys /= episode_steps
        average_redundancys /= episode_steps
        average_sensing_costs /= episode_steps
        average_transmission_costs /= episode_steps
        
        result = {
            'label': self._label,
            'episode_length': episode_steps,
            'episode_return': episode_return,
            'steps_per_second': steps_per_second,
            'cumulative_aovs': cumulative_aovs,
            'cumulative_costs': cumulative_costs,
            'average_aovs': average_aovs,
            'average_costs': average_costs,
            'average_timelinesss': average_timelinesss,
            'average_consistencys': average_consistencys,
            'average_redundancys': average_redundancys,
            'average_sensing_costs': average_sensing_costs,
            'average_transmission_costs': average_transmission_costs,
        }
        result.update(counts)

        for observer in self._observers:
            result.update(observer.get_metrics())
        return result

    def run(self,
            num_episodes: Optional[int] = None,
            num_steps: Optional[int] = None):
        """Perform the run loop.

        Run the environment loop either for `num_episodes` episodes or for at
        least `num_steps` steps (the last episode is always run until completion,
        so the total number of steps may be slightly more than `num_steps`).
        At least one of these two arguments has to be None.

        Upon termination of an episode a new episode will be started. If the number
        of episodes and the number of steps are not given then this will interact
        with the environment infinitely.

        Args:
        num_episodes: number of episodes to run the loop for.
        num_steps: minimal number of steps to run the loop for.

        Raises:
        ValueError: If both 'num_episodes' and 'num_steps' are not None.
        """        
        if not (num_episodes is None or num_steps is None):
            raise ValueError('Either "num_episodes" or "num_steps" should be None.')

        def should_terminate(episode_count: int, step_count: int) -> bool:
            return ((num_episodes is not None and episode_count >= num_episodes) or
                    (num_steps is not None and step_count >= num_steps))
    
        episode_count, step_count = 0, 0
        if self._label == 'Evaluator_Loop':
            file_name = init_file_name()
        with signals.runtime_terminator():
            while not should_terminate(episode_count, step_count):
                result = self.run_episode()
                episode_count += 1
                step_count += result['episode_length']
                # Log the given episode results.
                if step_count % 15000 and self._label == 'Evaluator_Loop':
                    save_obj(self._environment, file_name["temple_environment"])
                self._logger.write(result)
# Placeholder for an EnvironmentLoop alias


class EnvironmentLoopforD4PG(base.Worker):
    """A simple RL environment loop.

    This takes `Environment` and `Actor` instances and coordinates their
    interaction. Agent is updated if `should_update=True`. This can be used as:

        loop = EnvironmentLoop(environment, actor)
        loop.run(num_episodes)

    A `Counter` instance can optionally be given in order to maintain counts
    between different Acme components. If not given a local Counter will be
    created to maintain counts between calls to the `run` method.

    A `Logger` instance can also be passed in order to control the output of the
    loop. If not given a platform-specific default logger will be used as defined
    by utils.loggers.make_default_logger. A string `label` can be passed to easily
    change the label associated with the default logger; this is ignored if a
    `Logger` instance is given.

    A list of 'Observer' instances can be specified to generate additional metrics
    to be logged by the logger. They have access to the 'Environment' instance,
    the current timestep datastruct and the current action.
    """

    def __init__(
        self,
        environment,
        actor: base.Actor,
        counter: Optional[counting.Counter] = None,
        logger: Optional[loggers.Logger] = None,
        should_update: bool = True,
        label: str = 'environment_loop',
        observers: Sequence[observers_lib.EnvLoopObserver] = (),
    ):
        # Internalize agent and environment.
        self._environment = environment
        self._actor = actor
        self._label = label
        self._counter = counter or counting.Counter()
        self._logger = logger or loggers.make_default_logger(label)
        self._should_update = should_update
        self._observers = observers

    def run_episode(self) -> loggers.LoggingData:
        """Run one episode.

        Each episode is a loop which interacts first with the environment to get an
        observation and then give that observation to the agent in order to retrieve
        an action.

        Returns:
        An instance of `loggers.LoggingData`.
        """
        # Reset any counts and start the environment.
        start_time = time.time()
        episode_steps = 0

        # For evaluation, this keeps track of the total undiscounted reward
        # accumulated during the episode.
        episode_return = tree.map_structure(_generate_zeros_from_spec,
                                            self._environment.reward_spec())
        timestep = self._environment.reset()

        # Make the first observation.
        self._actor.observe_first(timestep)
        for observer in self._observers:
            # Initialize the observer with the current state of the env after reset
            # and the initial timestep.
            observer.observe_first(self._environment, timestep)

        cumulative_aovs: float = 0
        cumulative_costs: float = 0
        average_aovs: float = 0
        average_costs: float = 0
        average_timelinesss: float = 0
        average_consistencys: float = 0
        average_redundancys: float = 0
        average_sensing_costs: float = 0
        average_transmission_costs: float = 0         
        
        # Run an episode.
        while not timestep.last():
            # Generate an action from the agent's policy and step the environment.
            action = self._actor.select_action(timestep.observation)
            timestep, cumulative_aov, cumulative_cost, average_aov, average_cost, average_timeliness, average_consistency, average_redundancy, average_sensing_cost, average_transmission_cost = self._environment.step(action)
            
            cumulative_aovs += cumulative_aov
            cumulative_costs += cumulative_cost
            average_aovs += average_aov
            average_costs += average_cost
            average_timelinesss += average_timeliness
            average_consistencys += average_consistency
            average_redundancys += average_redundancy
            average_sensing_costs += average_sensing_cost
            average_transmission_costs += average_transmission_cost
            
            # Have the agent observe the timestep and let the actor update itself.
            self._actor.observe(action=action, next_timestep=timestep)
            for observer in self._observers:
                # One environment step was completed. Observe the current state of the
                # environment, the current timestep and the action.
                observer.observe(self._environment, timestep, action)
            if self._should_update:
                self._actor.update()
            # Book-keeping.
            episode_steps += 1
            # Equivalent to: episode_return += timestep.reward
            # We capture the return value because if timestep.reward is a JAX
            # DeviceArray, episode_return will not be mutated in-place. (In all other
            # cases, the returned episode_return will be the same object as the
            # argument episode_return.)
            episode_return = tree.map_structure(operator.iadd,
                                                episode_return,
                                                timestep.reward)

        # Record counts.
        counts = self._counter.increment(episodes=1, steps=episode_steps)

        # Collect the results and combine with counts.
        steps_per_second = episode_steps / (time.time() - start_time)
        average_aovs /= episode_steps
        average_costs /= episode_steps
        average_timelinesss /= episode_steps
        average_consistencys /= episode_steps
        average_redundancys /= episode_steps
        average_sensing_costs /= episode_steps
        average_transmission_costs /= episode_steps
        
        result = {
            'label': self._label,
            'episode_length': episode_steps,
            'episode_return': episode_return,
            'steps_per_second': steps_per_second,
            'cumulative_aovs': cumulative_aovs,
            'cumulative_costs': cumulative_costs,
            'average_aovs': average_aovs,
            'average_costs': average_costs,
            'average_timelinesss': average_timelinesss,
            'average_consistencys': average_consistencys,
            'average_redundancys': average_redundancys,
            'average_sensing_costs': average_sensing_costs,
            'average_transmission_costs': average_transmission_costs,
        }
        result.update(counts)

        for observer in self._observers:
            result.update(observer.get_metrics())
        return result

    def run(self,
            num_episodes: Optional[int] = None,
            num_steps: Optional[int] = None):
        """Perform the run loop.

        Run the environment loop either for `num_episodes` episodes or for at
        least `num_steps` steps (the last episode is always run until completion,
        so the total number of steps may be slightly more than `num_steps`).
        At least one of these two arguments has to be None.

        Upon termination of an episode a new episode will be started. If the number
        of episodes and the number of steps are not given then this will interact
        with the environment infinitely.

        Args:
        num_episodes: number of episodes to run the loop for.
        num_steps: minimal number of steps to run the loop for.

        Raises:
        ValueError: If both 'num_episodes' and 'num_steps' are not None.
        """        
        if not (num_episodes is None or num_steps is None):
            raise ValueError('Either "num_episodes" or "num_steps" should be None.')

        def should_terminate(episode_count: int, step_count: int) -> bool:
            return ((num_episodes is not None and episode_count >= num_episodes) or
                    (num_steps is not None and step_count >= num_steps))
    
        episode_count, step_count = 0, 0
        with signals.runtime_terminator():
            while not should_terminate(episode_count, step_count):
                result = self.run_episode()
                episode_count += 1
                step_count += result['episode_length']
                # Log the given episode results.
                self._logger.write(result)
# Placeholder for an EnvironmentLoop alias



def _generate_zeros_from_spec(spec: specs.Array) -> np.ndarray:
    return np.zeros(spec.shape, spec.dtype)

