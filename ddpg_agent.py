import numpy as np
import random
import copy
from collections import namedtuple, deque

from ddpg_model import Actor, Critic

import torch
import torch.nn.functional as F
import torch.optim as optim

BUFFER_SIZE = int(1e6)  # replay buffer size
BATCH_SIZE = 512      # minibatch size
GAMMA = 0.99       # discount factor
TAU = 1e-3              # for soft update of target parameters
LR_ACTOR = 5e-5         # learning rate of the actor 
LR_CRITIC = 5e-5        # learning rate of the critic
WEIGHT_DECAY = 0.0        # L2 weight decay
LEARN_N_INTERVAL = 20
LEARN_N_TIMES = 10

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")



class Agent():
    """Interacts with and learns from the environment."""
    
    class AgentResourcePool():
        def __init__(self, state_size, action_size, random_seed):
        
            self.actor_local =  Actor(state_size, action_size, random_seed).to(device)
            self.actor_target =  Actor(state_size, action_size, random_seed).to(device)
            self.actor_optimizer =  optim.Adam(self.actor_local.parameters(), lr=LR_ACTOR)

            # Critic Network (w/ Target Network)
            self.critic_local =   Critic(state_size, action_size, random_seed).to(device)
            self.critic_target =  Critic(state_size, action_size, random_seed).to(device)
            self.critic_optimizer =  optim.Adam(self.critic_local.parameters(), lr=LR_CRITIC, weight_decay=WEIGHT_DECAY)
            self.memory = ReplayBuffer(action_size, BUFFER_SIZE, BATCH_SIZE, random_seed)   


    resourcePool = None 
       
    def __init__(self, state_size, action_size, random_seed):
        """Initialize an Agent object.
        
        Params
        ======
            state_size (int): dimension of each state
            action_size (int): dimension of each action
            random_seed (int): random seed
        """
        self.state_size = state_size
        self.action_size = action_size
        self.seed = random.seed(random_seed)


        # Noise process
        self.noise = OUNoise(action_size, random_seed)
        if Agent.resourcePool is None:
            Agent.resourcePool = Agent.AgentResourcePool(state_size, action_size, random_seed)
           

    
    def step(self, time_step, state, action, reward, next_state, done):
        """Save experience in replay memory, and use random sample from buffer to learn."""
        # Save experience / reward
        Agent.resourcePool.memory.add(state, action, reward, next_state, done)

        if time_step % LEARN_N_INTERVAL != 0:
            #print('skip timestep ',time_step)
            return

        # Learn, if enough samples are available in memory
        if len(Agent.resourcePool.memory) > BATCH_SIZE:
            #print('learning')
            for i in range (LEARN_N_TIMES):
                experiences = Agent.resourcePool.memory.sample()
                self.learn(experiences, GAMMA)

    def act(self, state, add_noise=True):
        """Returns actions for given state as per current policy."""
        state = torch.from_numpy(state).float().to(device)
        Agent.resourcePool.actor_local.eval()
        with torch.no_grad():
            action = Agent.resourcePool.actor_local(state).cpu().data.numpy()
        Agent.resourcePool.actor_local.train()
        if add_noise:
            action += self.noise.sample()
        return np.clip(action, -1, 1)

    def reset(self):
        self.noise.reset()

    def learn(self, experiences, gamma):
        """Update policy and value parameters using given batch of experience tuples.
        Q_targets = r + γ * critic_target(next_state, actor_target(next_state))
        where:
            actor_target(state) -> action
            critic_target(state, action) -> Q-value

        Params
        ======
            experiences (Tuple[torch.Tensor]): tuple of (s, a, r, s', done) tuples 
            gamma (float): discount factor
        """
        states, actions, rewards, next_states, dones = experiences

        # ---------------------------- update critic ---------------------------- #
        # Get predicted next-state actions and Q values from target models
        actions_next = Agent.resourcePool.actor_target(next_states)
        Q_targets_next = Agent.resourcePool.critic_target(next_states, actions_next)
        # Compute Q targets for current states (y_i)
        Q_targets = rewards + (gamma * Q_targets_next * (1 - dones))
        # Compute critic loss
        Q_expected = Agent.resourcePool.critic_local(states, actions)
        critic_loss = F.mse_loss(Q_expected, Q_targets)
        # Minimize the loss
        Agent.resourcePool.critic_optimizer.zero_grad()
        critic_loss.backward()
        Agent.resourcePool.critic_optimizer.step()

        # ---------------------------- update actor ---------------------------- #
        # Compute actor loss
        actions_pred = Agent.resourcePool.actor_local(states)
        actor_loss = -Agent.resourcePool.critic_local(states, actions_pred).mean()
        # Minimize the loss
        Agent.resourcePool.actor_optimizer.zero_grad()
        actor_loss.backward()
        Agent.resourcePool.actor_optimizer.step()

        # ----------------------- update target networks ----------------------- #
        self.soft_update(Agent.resourcePool.critic_local, Agent.resourcePool.critic_target, TAU)
        self.soft_update(Agent.resourcePool.actor_local, Agent.resourcePool.actor_target, TAU)                     

    def soft_update(self, local_model, target_model, tau):
        """Soft update model parameters.
        θ_target = τ*θ_local + (1 - τ)*θ_target

        Params
        ======
            local_model: PyTorch model (weights will be copied from)
            target_model: PyTorch model (weights will be copied to)
            tau (float): interpolation parameter 
        """
        for target_param, local_param in zip(target_model.parameters(), local_model.parameters()):
            target_param.data.copy_(tau*local_param.data + (1.0-tau)*target_param.data)

class OUNoise:
    """Ornstein-Uhlenbeck process."""

    def __init__(self, size, seed, mu=0., theta=0.15, sigma=0.2):
        """Initialize parameters and noise process."""
        self.mu = mu * np.ones(size)
        self.theta = theta
        self.sigma = sigma
        self.seed = random.seed(seed)
        self.reset()

    def reset(self):
        """Reset the internal state (= noise) to mean (mu)."""
        self.state = copy.copy(self.mu)

    def sample(self):
        """Update internal state and return it as a noise sample."""
        x = self.state
        dx = self.theta * (self.mu - x) + self.sigma * np.array([random.random() for i in range(len(x))])
        self.state = x + dx
        return self.state

class ReplayBuffer:
    """Fixed-size buffer to store experience tuples."""

    def __init__(self, action_size, buffer_size, batch_size, seed):
        """Initialize a ReplayBuffer object.
        Params
        ======
            buffer_size (int): maximum size of buffer
            batch_size (int): size of each training batch
        """
        self.action_size = action_size
        self.memory = deque(maxlen=buffer_size)  # internal memory (deque)
        self.batch_size = batch_size
        self.experience = namedtuple("Experience", field_names=["state", "action", "reward", "next_state", "done"])
        self.seed = random.seed(seed)
    
    def add(self, state, action, reward, next_state, done):
        """Add a new experience to memory."""
        e = self.experience(state, action, reward, next_state, done)
        self.memory.append(e)
    
    def sample(self):
        """Randomly sample a batch of experiences from memory."""
        experiences = random.sample(self.memory, k=self.batch_size)

        states = torch.from_numpy(np.vstack([e.state for e in experiences if e is not None])).float().to(device)
        actions = torch.from_numpy(np.vstack([e.action for e in experiences if e is not None])).float().to(device)
        rewards = torch.from_numpy(np.vstack([e.reward for e in experiences if e is not None])).float().to(device)
        next_states = torch.from_numpy(np.vstack([e.next_state for e in experiences if e is not None])).float().to(device)
        dones = torch.from_numpy(np.vstack([e.done for e in experiences if e is not None]).astype(np.uint8)).float().to(device)

        return (states, actions, rewards, next_states, dones)

    def __len__(self):
        """Return the current size of internal memory."""
        return len(self.memory)
