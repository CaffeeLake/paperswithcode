#!/usr/bin/env python3
"""
Trigger a manual ArXiv sync (if scheduler is running).
"""

import os
from pathlib import Path

def main():
    trigger_file = Path("trigger_sync.txt")
    
    # Create trigger file
    trigger_file.touch()
    
    print("🔄 Manual sync triggered!")
    print("💡 If the scheduler is running, it will sync within 1 minute.")
    print("📋 Check the logs: tail -f local_scheduler.log")

if __name__ == "__main__":
    main()
