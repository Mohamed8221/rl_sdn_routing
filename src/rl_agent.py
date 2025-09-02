#!/usr/bin/env python3

import json
import logging
import os
import numpy as np
from flask import Flask, request, jsonify
import tensorflow as tf
import time

# Configure logging
logging.basicConfig(filename='logs/rl_agent.log', level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class QLearningAgent:
    def __init__(self, config_path='data/config/rl_config.json', paths_path='data/config/possible_paths.json'):
        try:
            if not os.path.exists(config_path):
                logger.error("Configuration file %s not found", config_path)
                raise FileNotFoundError(f"Configuration file {config_path} not found")
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            required_keys = ['state_size', 'learning_rate', 'discount_factor', 'save_interval']
            for key in required_keys:
                if key not in config:
                    logger.error("Missing key '%s' in %s", key, config_path)
                    raise KeyError(f"Missing key '{key}' in {config_path}")
            
            self.state_size = config['state_size']
            self.learning_rate = config['learning_rate']
            self.discount_factor = config['discount_factor']
            self.save_interval = config['save_interval']
            
            if not os.path.exists(paths_path):
                logger.error("Possible paths file %s not found", paths_path)
                raise FileNotFoundError(f"Possible paths file {paths_path} not found")
            
            with open(paths_path, 'r') as f:
                self.possible_paths = json.load(f)
            
            self.q_table = {}
            self.initialize_q_table()
            self.model = self.build_dqn_model()
            self.recent_rewards = []
            self.total_steps = 0
            logger.info("Q-Learning agent initialized with state_size=%s, lr=%s, discount=%s, save_interval=%s",
                        self.state_size, self.learning_rate, self.discount_factor, self.save_interval)
            logger.info("Initialized qlearning agent for topology with %s paths", len(self.possible_paths))
        except Exception as e:
            logger.error("Failed to initialize Q-Learning agent: %s", e)
            raise

    def initialize_q_table(self):
        for path_key in self.possible_paths:
            for path in self.possible_paths[path_key]:
                path_str = str(path)
                if path_str not in self.q_table:
                    self.q_table[path_str] = np.zeros(self.state_size)
                    logger.debug("Initialized Q-table for path %s", path_str)

    def build_dqn_model(self):
        model = tf.keras.Sequential([
            tf.keras.layers.Dense(24, activation='relu', input_shape=(self.state_size,)),
            tf.keras.layers.Dense(24, activation='relu'),
            tf.keras.layers.Dense(1, activation='linear')
        ])
        model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate), loss='mse')
        logger.info("DQN model built with input shape (%s,)", self.state_size)
        return model

    def get_action(self, state, src, dst):
        path_key = f"{src}->{dst}"
        if path_key not in self.possible_paths:
            logger.error("Invalid src-dst pair: %s", path_key)
            return None, None
        
        paths = self.possible_paths[path_key]
        if not paths:
            logger.error("No paths available for %s", path_key)
            return None, None
        
        state = np.array(state).reshape(1, -1)
        q_values = []
        for path in paths:
            path_str = str(path)
            if path_str not in self.q_table:
                self.q_table[path_str] = np.zeros(self.state_size)
            q_value = self.model.predict(state, verbose=0)[0][0]
            q_values.append(q_value)
        
        action_idx = np.argmax(q_values)
        chosen_path = paths[action_idx]
        logger.debug("Selected path %s for state %s, src=%s, dst=%s", chosen_path, state, src, dst)
        return chosen_path, action_idx

    def update_q_table(self, state, action, reward, next_state):
        action_str = str(action)
        if action_str not in self.q_table:
            self.q_table[action_str] = np.zeros(self.state_size)
        
        state = np.array(state)
        next_state = np.array(next_state)
        current_q = self.q_table[action_str]
        next_max_q = max([self.model.predict(np.array([next_state]), verbose=0)[0][0] for path in self.q_table])
        
        self.q_table[action_str] = (1 - self.learning_rate) * current_q + self.learning_rate * (reward + self.discount_factor * next_max_q)
        self.recent_rewards.append(reward)
        self.total_steps += 1
        
        if self.total_steps % self.save_interval == 0:
            self.model.save(f'models/dqn_model_{self.total_steps}.h5')
            logger.info("Saved DQN model at step %s", self.total_steps)

agent = None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'agent_initialized': agent is not None,
        'timestamp': time.time()
    })

@app.route('/get_path', methods=['POST'])
def get_path():
    try:
        data = request.get_json()
        if not data:
            logger.error("No JSON data in request")
            return jsonify({'error': 'No JSON data provided'}), 400
        
        src = data.get('src')
        dst = data.get('dst')
        state = data.get('state')
        
        if not src or not dst:
            logger.error("Missing src or dst in payload: %s", data)
            return jsonify({'error': 'Missing src or dst'}), 400
        
        if not isinstance(state, list) or len(state) != agent.state_size:
            logger.error("Invalid state format or length: %s (expected length %s)", state, agent.state_size)
            return jsonify({'error': f'State must be a list of length {agent.state_size}'}), 400
        
        path_key = f"{src}->{dst}"
        if path_key not in agent.possible_paths:
            logger.error("Invalid src-dst pair: %s", path_key)
            return jsonify({'error': f'Invalid src-dst pair: {path_key}'}), 400
        
        path, action_idx = agent.get_action(state, src, dst)
        if path is None:
            logger.error("No valid path found for %s", path_key)
            return jsonify({'error': 'No valid path found'}), 400
        
        logger.info("Returning path %s for %s", path, path_key)
        return jsonify({
            'path': path,
            'action_idx': action_idx
        })
    except Exception as e:
        logger.error("Error in get_path: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/update', methods=['POST'])
def update():
    try:
        data = request.get_json()
        state = data.get('state')
        action = data.get('action')
        reward = data.get('reward')
        next_state = data.get('next_state')
        
        if not all([state, action, reward is not None, next_state]):
            logger.error("Missing required fields in update payload: %s", data)
            return jsonify({'error': 'Missing required fields'}), 400
        
        if not isinstance(state, list) or len(state) != agent.state_size:
            logger.error("Invalid state format or length: %s", state)
            return jsonify({'error': f'State must be a list of length {agent.state_size}'}), 400
        
        if not isinstance(next_state, list) or len(next_state) != agent.state_size:
            logger.error("Invalid next_state format or length: %s", next_state)
            return jsonify({'error': f'Next_state must be a list of length {agent.state_size}'}), 400
        
        agent.update_q_table(state, action, reward, next_state)
        logger.info("Updated Q-table with reward %s", reward)
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error("Error in update: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/stats', methods=['GET'])
def stats():
    try:
        return jsonify({
            'count': agent.total_steps,
            'recent_rewards': agent.recent_rewards[-100:],
            'paths': {k: v.tolist() for k, v in agent.q_table.items()}
        })
    except Exception as e:
        logger.error("Error in stats: %s", e)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    os.makedirs('logs', exist_ok=True)
    os.makedirs('models', exist_ok=True)
    try:
        agent = QLearningAgent()
        logger.info("RL agent initialized successfully")
        logger.info("Starting RL Agent Flask server on port 5000...")
        app.run(host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        logger.error("Failed to start RL agent: %s", e)
        raise
