import pickle
import uuid
import os
import datetime

def save_obj(obj, name):
    """
    Saves given object as a pickle file
    :param obj:
    :param name:
    :return:
    """
    if name[-4:] != ".pkl":
        name += ".pkl"
    with open(name, 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)


def load_obj(name):
    """
    Loads a pickle file object
    :param name:
    :return:
    """
    with open(name, 'rb') as f:
        return pickle.load(f)


def init_file_name():
    dayTime = datetime.datetime.now().strftime('%Y-%m-%d')
    hourTime = datetime.datetime.now().strftime('%H-%M-%S')
    pwd = "/home/neardws/Documents/AoV-Journal-Algorithm/Data/" + dayTime + '-' + hourTime

    if not os.path.exists(pwd):
        os.makedirs(pwd)

    uuid_str = uuid.uuid4().hex
    init_environment_with_reward_matrix_name = pwd + '/' + 'init_environment_%s_with_reward_matrix.pkl' % uuid_str
    init_environment_without_reward_matrix_name = pwd + '/' + 'init_environment_%s_without_reward_matrix.pkl' % uuid_str
    
    temple_environment = pwd + '/' + 'temple_environment_%s_with_reward_matrix.pkl' % uuid_str    
    
    return {
        "init_environment_with_reward_matrix_name": init_environment_with_reward_matrix_name,
        "init_environment_without_reward_matrix_name": init_environment_without_reward_matrix_name,
        "temple_environment": temple_environment,
    }
    
def init_policy_file_name():
    dayTime = datetime.datetime.now().strftime('%Y-%m-%d')
    hourTime = datetime.datetime.now().strftime('%H-%M-%S')
    pwd = "/home/neardws/Documents/AoV-Journal-Algorithm/Data/" + dayTime + '-' + hourTime + "policy"

    if not os.path.exists(pwd):
        os.makedirs(pwd)

    uuid_str = uuid.uuid4().hex
    
    edge_policy_network = pwd + '/' + 'edge_policy_%s.pkl' % uuid_str
    vehicle_policy_network = pwd + '/' + 'vehicle_policy_%s.pkl' % uuid_str
    target_edge_policy_network = pwd + '/' + 'target_edge_policy_%s.pkl' % uuid_str
    target_vehicle_policy_network = pwd + '/' + 'target_vehicle_policy_%s.pkl' % uuid_str
    
    return {
        "edge_policy_network": edge_policy_network,
        "vehicle_policy_network": vehicle_policy_network,
        "target_edge_policy_network": target_edge_policy_network,
        "target_vehicle_policy_network": target_vehicle_policy_network,
    }