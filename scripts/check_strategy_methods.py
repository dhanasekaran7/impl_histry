# ==================== scripts/check_strategy_methods.py ====================
"""
Quick script to check if your strategy methods need updating
"""

import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

def check_strategy_methods():
    """Check if strategy methods are updated"""
    
    print("🔍 Checking Strategy Methods")
    print("=" * 40)
    
    try:
        strategy_file = project_root / "src" / "strategy" / "option_integrated_pine_script.py"
        
        if not strategy_file.exists():
            print("❌ Strategy file not found!")
            return False
        
        with open(strategy_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for key indicators of updated methods
        checks = [
            ("Option Chain Manager Usage", "self.option_chain_manager.get_option_chain" in content),
            ("Fallback Strike Calculation", "FALLBACK: Calculate ATM from spot price" in content),
            ("Emergency Fallback", "EMERGENCY FALLBACK" in content),
            ("Robust Error Handling", "Could not get option chain for strike calculation, using fallback" in content),
            ("Fixed LTP Method", "FALLBACK: Try direct API call if option chain failed" in content)
        ]
        
        print("Method Status:")
        all_updated = True
        
        for check_name, condition in checks:
            status = "✅ UPDATED" if condition else "❌ NEEDS UPDATE"
            print(f"  {check_name}: {status}")
            if not condition:
                all_updated = False
        
        print("=" * 40)
        
        if all_updated:
            print("✅ ALL METHODS ARE UPDATED!")
            print("✅ Your strategy is ready for main.py")
            return True
        else:
            print("⚠️  METHODS NEED UPDATING")
            print("⚠️  Replace the 4 methods in your strategy file")
            return False
        
    except Exception as e:
        print(f"❌ Error checking methods: {e}")
        return False

if __name__ == "__main__":
    result = check_strategy_methods()
    
    if not result:
        print("\n🔧 NEXT STEPS:")
        print("1. Open: src/strategy/option_integrated_pine_script.py")
        print("2. Replace the 4 methods with fixed versions")
        print("3. Run this check again")
        print("4. Then run main.py")
    else:
        print("\n🚀 READY TO RUN: python main.py")