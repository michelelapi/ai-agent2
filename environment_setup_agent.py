#!/usr/bin/env python3
import os
import re
import sys
import subprocess
import json
import base64
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Any
import requests
from github import Github, Repository, ContentFile
import markdown
from bs4 import BeautifulSoup
import inquirer

class EnvironmentSetupAgent:
    """
    AI Agent to help with setting up development environments for microservices
    based on README.md files from a GitHub repository.
    """
    
    def __init__(self, github_token: str, repo_name: str):
        """
        Initialize the agent with GitHub credentials and repository information.
        
        Args:
            github_token: Personal access token for GitHub
            repo_name: Full name of the repository (e.g., "organization/repo")
        """
        self.github_token = github_token
        self.repo_name = repo_name
        self.github_client = Github(github_token)
        self.repo = self.github_client.get_repo(repo_name)
        self.projects = []
        self.tools_cache = {
            "general": {
                "git": {
                    "installation": "sudo apt-get update && sudo apt-get install -y git",
                    "verification": "git --version",
                },
                "docker": {
                    "installation": """
                        sudo apt-get update
                        sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
                        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
                        sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
                        sudo apt-get update
                        sudo apt-get install -y docker-ce docker-ce-cli containerd.io
                        sudo usermod -aG docker $USER
                    """,
                    "verification": "docker --version",
                },
                "docker-compose": {
                    "installation": """
                        sudo curl -L "https://github.com/docker/compose/releases/download/v2.18.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
                        sudo chmod +x /usr/local/bin/docker-compose
                    """,
                    "verification": "docker-compose --version",
                },
                "nvm": {
                    "installation": """
                        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh | bash
                        export NVM_DIR="$HOME/.nvm"
                        [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
                    """,
                    "verification": "nvm --version",
                },
                "node": {
                    "installation": "nvm install --lts",
                    "verification": "node --version",
                    "dependencies": ["nvm"]
                },
                "npm": {
                    "installation": "", # Comes with Node.js
                    "verification": "npm --version",
                    "dependencies": ["node"]
                },
                "java": {
                    "installation": "sudo apt-get update && sudo apt-get install -y openjdk-17-jdk",
                    "verification": "java -version",
                },
                "maven": {
                    "installation": "sudo apt-get update && sudo apt-get install -y maven",
                    "verification": "mvn -version",
                },
                "gradle": {
                    "installation": """
                        wget -q https://services.gradle.org/distributions/gradle-8.3-bin.zip -P /tmp
                        sudo unzip -d /opt/gradle /tmp/gradle-*.zip
                        echo 'export PATH=$PATH:/opt/gradle/gradle-8.3/bin' >> ~/.bashrc
                        export PATH=$PATH:/opt/gradle/gradle-8.3/bin
                    """,
                    "verification": "gradle -version",
                },
                "python3": {
                    "installation": "sudo apt-get update && sudo apt-get install -y python3 python3-pip",
                    "verification": "python3 --version && pip3 --version",
                },
                "mongodb": {
                    "installation": """
                        wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
                        echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
                        sudo apt-get update
                        sudo apt-get install -y mongodb-org
                        sudo systemctl start mongod
                        sudo systemctl enable mongod
                    """,
                    "verification": "mongod --version",
                },
                "postgresql": {
                    "installation": """
                        sudo apt-get update
                        sudo apt-get install -y postgresql postgresql-contrib
                        sudo systemctl start postgresql
                        sudo systemctl enable postgresql
                    """,
                    "verification": "psql --version",
                },
                "mysql": {
                    "installation": """
                        sudo apt-get update
                        sudo apt-get install -y mysql-server
                        sudo systemctl start mysql
                        sudo systemctl enable mysql
                        sudo mysql_secure_installation
                    """,
                    "verification": "mysql --version",
                },
                "redis": {
                    "installation": """
                        sudo apt-get update
                        sudo apt-get install -y redis-server
                        sudo systemctl start redis
                        sudo systemctl enable redis
                    """,
                    "verification": "redis-cli --version",
                },
                "vscode": {
                    "installation": """
                        wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
                        sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
                        sudo sh -c 'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
                        rm -f packages.microsoft.gpg
                        sudo apt update
                        sudo apt install -y code
                    """,
                    "verification": "code --version",
                },
                "intellij-idea": {
                    "installation": """
                        sudo snap install intellij-idea-community --classic
                    """,
                    "verification": "snap info intellij-idea-community",
                }
            }
        }
        
    def discover_projects(self):
        """
        Scan the repository to find all projects (assumed to be directories containing a README.md file).
        """
        contents = self.repo.get_contents("")
        self.projects = []
        
        # Process all directories at the root level
        for content in contents:
            if content.type == "dir":
                try:
                    readme = self.repo.get_contents(f"{content.path}/README.md")
                    self.projects.append({
                        "name": content.name,
                        "path": content.path,
                        "readme_content": base64.b64decode(readme.content).decode('utf-8')
                    })
                except Exception:
                    # Skip directories without a README.md
                    continue
        
        return self.projects
    
    def parse_readme(self, readme_content: str) -> Dict[str, Any]:
        """
        Parse a README.md file to extract setup instructions and required tools.
        
        Args:
            readme_content: Content of the README.md file
            
        Returns:
            Dictionary containing extracted setup information
        """
        html = markdown.markdown(readme_content)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract information from the README
        setup_info = {
            "prerequisites": [],
            "environment_setup": [],
            "database_setup": [],
            "running_instructions": [],
            "ide_setup": []
        }
        
        # Look for prerequisites and required tools
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            heading_text = heading.text.lower()
            
            if any(term in heading_text for term in ["prerequisite", "requirement", "depend", "tool", "software"]):
                # Get all content until the next heading
                content = []
                for sibling in heading.next_siblings:
                    if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                        break
                    if sibling.name == 'ul':
                        for li in sibling.find_all('li'):
                            content.append(li.text.strip())
                    elif sibling.name == 'p':
                        content.append(sibling.text.strip())
                
                setup_info["prerequisites"].extend(content)
            
            elif any(term in heading_text for term in ["setup", "install", "configur", "environ"]):
                content = []
                for sibling in heading.next_siblings:
                    if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                        break
                    if sibling.name in ['p', 'pre', 'code']:
                        content.append(sibling.text.strip())
                    elif sibling.name == 'ul':
                        for li in sibling.find_all('li'):
                            content.append(li.text.strip())
                
                setup_info["environment_setup"].extend(content)
            
            elif any(term in heading_text for term in ["database", "db", "data"]):
                content = []
                for sibling in heading.next_siblings:
                    if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                        break
                    if sibling.name in ['p', 'pre', 'code']:
                        content.append(sibling.text.strip())
                    elif sibling.name == 'ul':
                        for li in sibling.find_all('li'):
                            content.append(li.text.strip())
                
                setup_info["database_setup"].extend(content)
            
            elif any(term in heading_text for term in ["run", "start", "execute"]):
                content = []
                for sibling in heading.next_siblings:
                    if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                        break
                    if sibling.name in ['p', 'pre', 'code']:
                        content.append(sibling.text.strip())
                    elif sibling.name == 'ul':
                        for li in sibling.find_all('li'):
                            content.append(li.text.strip())
                
                setup_info["running_instructions"].extend(content)
            
            elif any(term in heading_text for term in ["ide", "intellij", "eclipse", "vscode", "editor"]):
                content = []
                for sibling in heading.next_siblings:
                    if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                        break
                    if sibling.name in ['p', 'pre', 'code']:
                        content.append(sibling.text.strip())
                    elif sibling.name == 'ul':
                        for li in sibling.find_all('li'):
                            content.append(li.text.strip())
                
                setup_info["ide_setup"].extend(content)
        
        # Analyze the README to detect required tools
        setup_info["detected_tools"] = self.detect_tools(readme_content)
        
        return setup_info
    
    def detect_tools(self, readme_content: str) -> List[str]:
        """
        Analyze README content to detect required tools and technologies.
        
        Args:
            readme_content: Content of the README.md file
            
        Returns:
            List of detected tools
        """
        tools = []
        # Keywords to look for various tools and technologies
        tool_patterns = {
            "java": r"\bjava\b|\bjdk\b|\bjre\b",
            "maven": r"\bmaven\b|\bmvn\b",
            "gradle": r"\bgradle\b",
            "node": r"\bnode(?:js)?\b",
            "npm": r"\bnpm\b",
            "python3": r"\bpython(?:3)?\b|\bpip(?:3)?\b",
            "docker": r"\bdocker\b",
            "docker-compose": r"\bdocker[ -]compose\b",
            "git": r"\bgit\b",
            "mongodb": r"\bmongo(?:db)?\b",
            "postgresql": r"\bpostgre(?:s|sql)?\b",
            "mysql": r"\bmysql\b",
            "redis": r"\bredis\b",
            "vscode": r"\bvs ?code\b|\bvisual studio code\b",
            "intellij-idea": r"\bintellij\b|\bidea\b"
        }
        
        for tool, pattern in tool_patterns.items():
            if re.search(pattern, readme_content, re.IGNORECASE):
                tools.append(tool)
        
        return tools
    
    def analyze_all_projects(self):
        """
        Analyze all discovered projects and extract setup information.
        
        Returns:
            Dictionary mapping project names to their setup information
        """
        project_info = {}
        
        for project in self.projects:
            project_info[project["name"]] = self.parse_readme(project["readme_content"])
        
        return project_info
    
    def check_tool_installed(self, tool_name: str) -> bool:
        """
        Check if a specific tool is already installed on the system.
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            True if the tool is installed, False otherwise
        """
        if tool_name not in self.tools_cache["general"]:
            print(f"Unknown tool: {tool_name}")
            return False
        
        verification_cmd = self.tools_cache["general"][tool_name]["verification"]
        try:
            result = subprocess.run(verification_cmd, shell=True, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            print(f"Error checking tool {tool_name}: {e}")
            return False
    
    def install_tool(self, tool_name: str) -> bool:
        """
        Install a specific tool on the system.
        
        Args:
            tool_name: Name of the tool to install
            
        Returns:
            True if installation was successful, False otherwise
        """
        if tool_name not in self.tools_cache["general"]:
            print(f"Unknown tool: {tool_name}")
            return False
        
        # Check if there are any dependencies
        tool_info = self.tools_cache["general"][tool_name]
        if "dependencies" in tool_info:
            for dependency in tool_info["dependencies"]:
                if not self.check_tool_installed(dependency):
                    print(f"Installing dependency: {dependency}")
                    if not self.install_tool(dependency):
                        print(f"Failed to install dependency: {dependency}")
                        return False
        
        installation_cmd = tool_info["installation"]
        try:
            print(f"Installing {tool_name}...")
            result = subprocess.run(installation_cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Installation failed: {result.stderr}")
                return False
            
            # Verify installation
            return self.check_tool_installed(tool_name)
        except Exception as e:
            print(f"Error installing tool {tool_name}: {e}")
            return False
    
    def setup_environment_for_project(self, project_name: str):
        """
        Set up the environment for a specific project.
        
        Args:
            project_name: Name of the project to set up
        """
        if not self.projects:
            self.discover_projects()
        
        project = next((p for p in self.projects if p["name"] == project_name), None)
        if not project:
            print(f"Project {project_name} not found")
            return
        
        setup_info = self.parse_readme(project["readme_content"])
        
        # Install detected tools
        for tool in setup_info["detected_tools"]:
            if not self.check_tool_installed(tool):
                print(f"Tool {tool} is required but not installed. Installing...")
                if self.install_tool(tool):
                    print(f"Successfully installed {tool}")
                else:
                    print(f"Failed to install {tool}")
        
        # Display setup instructions
        print("\n" + "="*50)
        print(f"Setup Guide for {project_name}")
        print("="*50)
        
        print("\nPrerequisites:")
        for item in setup_info["prerequisites"]:
            print(f"- {item}")
        
        print("\nEnvironment Setup:")
        for item in setup_info["environment_setup"]:
            print(f"- {item}")
        
        if setup_info["database_setup"]:
            print("\nDatabase Setup:")
            for item in setup_info["database_setup"]:
                print(f"- {item}")
        
        print("\nRunning Instructions:")
        for item in setup_info["running_instructions"]:
            print(f"- {item}")
        
        if setup_info["ide_setup"]:
            print("\nIDE Setup:")
            for item in setup_info["ide_setup"]:
                print(f"- {item}")
    
    def select_project_interactive(self):
        """
        Interactive project selection menu.
        
        Returns:
            Name of the selected project
        """
        if not self.projects:
            self.discover_projects()
        
        questions = [
            inquirer.List('project',
                          message="Select a project to set up:",
                          choices=[p["name"] for p in self.projects],
                         )
        ]
        answers = inquirer.prompt(questions)
        return answers['project']
    
    def run_interactive(self):
        """Run the agent in interactive mode."""
        print("🤖 Welcome to the Environment Setup Agent! 🚀")
        print("Discovering projects in the repository...")
        
        self.discover_projects()
        print(f"Found {len(self.projects)} projects with README.md files.")
        
        while True:
            print("\nWhat would you like to do?")
            questions = [
                inquirer.List('action',
                              message="Choose an action:",
                              choices=[
                                  "Set up environment for a specific project",
                                  "Install a specific tool",
                                  "List available projects",
                                  "List recommended tools",
                                  "Exit"
                              ],
                             )
            ]
            answers = inquirer.prompt(questions)
            
            if answers['action'] == "Set up environment for a specific project":
                project = self.select_project_interactive()
                self.setup_environment_for_project(project)
            
            elif answers['action'] == "Install a specific tool":
                tools = list(self.tools_cache["general"].keys())
                questions = [
                    inquirer.List('tool',
                                  message="Select a tool to install:",
                                  choices=tools,
                                 )
                ]
                answers = inquirer.prompt(questions)
                tool = answers['tool']
                if not self.check_tool_installed(tool):
                    if self.install_tool(tool):
                        print(f"Successfully installed {tool}")
                    else:
                        print(f"Failed to install {tool}")
                else:
                    print(f"{tool} is already installed")
            
            elif answers['action'] == "List available projects":
                print("\nAvailable projects:")
                for i, project in enumerate(self.projects, 1):
                    print(f"{i}. {project['name']}")
            
            elif answers['action'] == "List recommended tools":
                all_projects_info = self.analyze_all_projects()
                tool_frequency = {}
                
                for project, info in all_projects_info.items():
                    for tool in info["detected_tools"]:
                        tool_frequency[tool] = tool_frequency.get(tool, 0) + 1
                
                print("\nRecommended tools based on project requirements:")
                for tool, count in sorted(tool_frequency.items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / len(self.projects)) * 100
                    print(f"- {tool}: used in {count}/{len(self.projects)} projects ({percentage:.1f}%)")
                    if not self.check_tool_installed(tool):
                        print(f"  ❌ Not installed. Run 'Install a specific tool' to install it.")
                    else:
                        print(f"  ✅ Already installed")
            
            elif answers['action'] == "Exit":
                print("Thank you for using the Environment Setup Agent. Goodbye!")
                break


def main():
    """Main entry point for the script."""
    # Check for environment variables first
    github_token = os.environ.get("GITHUB_TOKEN")
    repo_name = os.environ.get("GITHUB_REPO")
    
    # If not set as environment variables, prompt the user
    if not github_token:
        github_token = input("Enter your GitHub Personal Access Token: ")
    
    if not repo_name:
        repo_name = input("Enter the repository name (e.g., 'organization/repo'): ")
    
    # Attempt to connect to GitHub with better error handling
    try:
        print(f"Connecting to GitHub repository: {repo_name}")
        agent = EnvironmentSetupAgent(github_token, repo_name)
        agent.run_interactive()
    except Exception as e:
        print(f"\nError connecting to GitHub: {e}")
        print("\nPossible causes:")
        print("1. The GitHub token doesn't have sufficient permissions")
        print("2. The repository name format is incorrect (should be 'owner/repo')")
        print("3. The repository doesn't exist or you don't have access to it")
        print("\nWould you like to try again with different credentials? (y/n)")
        retry = input().lower().strip()
        if retry == 'y':
            github_token = input("Enter your GitHub Personal Access Token: ")
            repo_name = input("Enter the repository name (e.g., 'organization/repo'): ")
            try:
                agent = EnvironmentSetupAgent(github_token, repo_name)
                agent.run_interactive()
            except Exception as e:
                print(f"\nStill encountering errors: {e}")
                print("Please check your credentials and try again later.")
        else:
            print("Exiting. Please check your credentials and try again.")


if __name__ == "__main__":
    main()
