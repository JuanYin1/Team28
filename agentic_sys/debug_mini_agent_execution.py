#!/usr/bin/env python3
"""
Debug script to test Mini-Agent execution and identify hanging issues
"""

import subprocess
import tempfile
import time
from pathlib import Path

def test_mini_agent_path():
    """Test if Mini-Agent can be found and executed"""
    
    possible_paths = [
        "/Users/ria/Downloads/UCSD/CSE291P/Team28/Mini-Agent/.venv/bin/mini-agent",
        "./Mini-Agent/.venv/bin/mini-agent",
        "mini-agent"  # Global installation
    ]
    
    print("🔍 Testing Mini-Agent paths...")
    
    for path in possible_paths:
        print(f"Testing: {path}")
        
        # Test if path exists
        if Path(path).exists():
            print(f"  ✅ File exists: {path}")
            mini_agent_path = path
            break
        else:
            # Test if command is available
            result = subprocess.run(["which", path], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  ✅ Command found: {result.stdout.strip()}")
                mini_agent_path = path
                break
            else:
                print(f"  ❌ Not found: {path}")
    else:
        print("❌ No Mini-Agent executable found!")
        return None
    
    return mini_agent_path

def test_mini_agent_execution(mini_agent_path):
    """Test simple Mini-Agent execution"""
    
    print(f"\n🚀 Testing Mini-Agent execution: {mini_agent_path}")
    
    with tempfile.TemporaryDirectory() as temp_workspace:
        print(f"   Workspace: {temp_workspace}")
        
        # Simple test task
        test_task = "Create a file called 'test.txt' with content 'Hello World'"
        
        print(f"   Task: {test_task}")
        print("   Executing... (timeout: 30s)")
        
        try:
            start_time = time.time()
            
            process = subprocess.run([
                mini_agent_path,
                "--workspace", temp_workspace,
                "--task", test_task
            ], 
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
            )
            
            execution_time = time.time() - start_time
            
            print(f"\n📊 Results:")
            print(f"   Return code: {process.returncode}")
            print(f"   Execution time: {execution_time:.2f}s")
            print(f"   Success: {process.returncode == 0}")
            
            if process.stdout:
                print(f"\n📝 STDOUT (first 500 chars):")
                print(process.stdout[:500])
                if len(process.stdout) > 500:
                    print("... (truncated)")
            
            if process.stderr:
                print(f"\n❌ STDERR:")
                print(process.stderr)
            
            # Check if file was created
            test_file = Path(temp_workspace) / "test.txt"
            if test_file.exists():
                print(f"\n✅ File created successfully!")
                content = test_file.read_text()
                print(f"   Content: {content}")
            else:
                print(f"\n❌ Expected file 'test.txt' was not created")
                
        except subprocess.TimeoutExpired:
            print("\n⏰ TIMEOUT: Mini-Agent execution timed out after 30 seconds")
            print("This suggests the agent is hanging or waiting for input")
            return False
        except Exception as e:
            print(f"\n💥 ERROR: {e}")
            return False
    
    return process.returncode == 0

def main():
    """Main debug function"""
    
    print("🐛 Mini-Agent Execution Debug")
    print("=" * 50)
    
    # Test path detection
    mini_agent_path = test_mini_agent_path()
    
    if not mini_agent_path:
        print("\n❌ Cannot proceed without Mini-Agent executable")
        return
    
    # Test execution
    success = test_mini_agent_execution(mini_agent_path)
    
    if success:
        print("\n✅ Mini-Agent execution test passed!")
        print("   The evaluation system should work correctly.")
    else:
        print("\n❌ Mini-Agent execution failed!")
        print("   This explains why the evaluation system hangs.")
        print("\nPossible solutions:")
        print("   1. Check if Mini-Agent is properly installed")
        print("   2. Verify the virtual environment is activated")
        print("   3. Check for permission issues")
        print("   4. Test Mini-Agent manually from command line")

if __name__ == "__main__":
    main()