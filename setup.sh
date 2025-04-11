#!/bin/bash

# Setup script for Environment Setup Agent
# This script installs the necessary dependencies and sets up the agent

echo "🚀 Setting up the Environment Setup Agent..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
else
    echo "✅ Python 3 is already installed"
fi

# Create a virtual environment
echo "Creating a virtual environment..."
python3 -m pip install --user virtualenv
python3 -m virtualenv env
source env/bin/activate

# Install required packages
echo "Installing required packages..."
pip install PyGithub markdown beautifulsoup4 inquirer

# Download the environment setup agent
echo "Setting up the agent..."
wget -O environment_setup_agent.py https://github.com/DroneBase/ai-agent/main/environment_setup_agent.py
chmod +x environment_setup_agent.py

# Prompt for GitHub credentials
echo ""
echo "To use the Environment Setup Agent, you need to provide your GitHub credentials."
echo "The agent needs access to your repository to read README.md files."
echo ""
read -p "Enter your GitHub Personal Access Token: " github_token
read -p "Enter your GitHub repository name (e.g., 'organization/repo'): " github_repo

# Save credentials to environment variables
echo "export GITHUB_TOKEN='$github_token'" >> ~/.bashrc
echo "export GITHUB_REPO='$github_repo'" >> ~/.bashrc
source ~/.bashrc

echo ""
echo "✅ Environment Setup Agent is ready to use!"
echo ""
echo "To start the agent, run:"
echo "  source env/bin/activate"
echo "  ./environment_setup_agent.py"
echo ""
echo "You can also set up an alias for easier access:"
echo "  echo 'alias setup-agent=\"cd $(pwd) && source env/bin/activate && ./environment_setup_agent.py\"' >> ~/.bashrc"
echo "  source ~/.bashrc"
echo ""
echo "Then you can just type 'setup-agent' to start the tool."
