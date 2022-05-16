import sys
sys.path.append(r"/home/neardws/Documents/AoV-Journal-Algorithm/")

import environment_loop
from absl.testing import absltest
from Agents.MAD3PG import actors
from Test.environmentConfig_test import vehicularNetworkEnvConfig
from Environments.environment import vehicularNetworkEnv
from Environments import specs
from Agents.MAD3PG.networks import make_policy_network


class ActorTest(absltest.TestCase):


    def test_feedforward(self):

        config = vehicularNetworkEnvConfig()
        config.vehicle_list_seeds += [i for i in range(config.vehicle_number)]
        config.view_list_seeds += [i for i in range(config.view_number)]

        env = vehicularNetworkEnv(config)

        env_spec = specs.make_environment_spec(env)

        vehicle_policy_network = make_policy_network(env_spec.vehicle_actions)
        edge_policy_network = make_policy_network(env_spec.edge_actions)

        actor = actors.FeedForwardActor(
            vehicle_policy_network=vehicle_policy_network,
            edge_policy_network=edge_policy_network,
            vehicle_number=self._environment._config.vehicle_number,
            information_number=self._environment._config.information_number,
            sensed_information_number=self._environment._config.sensed_information_number,
            vehicle_observation_size=self._environment._vehicle_observation_size,
        )
        loop = environment_loop.EnvironmentLoop(env, actor)
        loop.run(20)


if __name__ == '__main__':
    absltest.main()