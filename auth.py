# auth.py - Authentication module
import hashlib
import json
from typing import Dict, Optional, List
from datetime import datetime
import os
from enum import Enum

class UserRole(Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"

class AuthenticationManager:
    def __init__(self, users_file: str = "users.json"):
        self.users_file = users_file
        self.users = self._load_users()
        
    def _load_users(self) -> Dict:
        """Load users from JSON file"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Default users
        default_users = {
            "admin": {
                "password": self._hash_password("admin123"),
                "role": UserRole.ADMIN.value,
                "created_at": datetime.now().isoformat(),
                "active": True
            },
            "engineer": {
                "password": self._hash_password("engineer123"),
                "role": UserRole.ENGINEER.value,
                "created_at": datetime.now().isoformat(),
                "active": True
            },
            "viewer": {
                "password": self._hash_password("viewer123"),
                "role": UserRole.VIEWER.value,
                "created_at": datetime.now().isoformat(),
                "active": True
            }
        }
        self._save_users(default_users)
        return default_users
    
    def _save_users(self, users: Dict):
        """Save users to JSON file"""
        with open(self.users_file, 'w') as f:
            json.dump(users, f, indent=2)
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user"""
        if username in self.users:
            user = self.users[username]
            if user['active'] and user['password'] == self._hash_password(password):
                return {
                    'username': username,
                    'role': user['role'],
                    'login_time': datetime.now().isoformat()
                }
        return None
    
    def add_user(self, username: str, password: str, role: str) -> bool:
        """Add new user"""
        if username in self.users:
            return False
        
        self.users[username] = {
            "password": self._hash_password(password),
            "role": role,
            "created_at": datetime.now().isoformat(),
            "active": True
        }
        self._save_users(self.users)
        return True
    
    def delete_user(self, username: str) -> bool:
        """Delete user"""
        if username in self.users and username != "admin":
            del self.users[username]
            self._save_users(self.users)
            return True
        return False
    
    def update_user_role(self, username: str, new_role: str) -> bool:
        """Update user role"""
        if username in self.users:
            self.users[username]['role'] = new_role
            self._save_users(self.users)
            return True
        return False
    
    def get_all_users(self) -> List[Dict]:
        """Get all users"""
        return [{'username': k, **v} for k, v in self.users.items() if k != 'admin']
    
    def has_permission(self, username: str, required_role: str) -> bool:
        """Check if user has required role"""
        if username in self.users:
            user_role = self.users[username]['role']
            role_levels = {
                UserRole.ADMIN.value: 3,
                UserRole.ENGINEER.value: 2,
                UserRole.VIEWER.value: 1
            }
            return role_levels.get(user_role, 0) >= role_levels.get(required_role, 0)
        return False