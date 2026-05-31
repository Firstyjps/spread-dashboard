import os
from typing import Dict

def update_env_file(env_path: str, updates: Dict[str, str]):
    """Update or append key-value pairs in a .env file."""
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
    # Parse existing keys
    key_indices = {}
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('#'):
            continue
        if '=' in line_stripped:
            key = line_stripped.split('=', 1)[0].strip()
            key_indices[key] = i
            
    # Update or append
    for key, value in updates.items():
        # Ensure value string is properly escaped if needed, 
        # but for simple API keys, direct assignment is fine
        new_line = f"{key}={value}\n"
        if key in key_indices:
            lines[key_indices[key]] = new_line
        else:
            lines.append(new_line)
            
    # Write back
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
