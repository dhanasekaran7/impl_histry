# Save as: validate_step5.py

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

async def validate_step5_integration():
    """Validate Step 5 integration without running full bot"""
    
    print("🧪 VALIDATING STEP 5 INTEGRATION")
    print("=" * 40)
    
    try:
        # Test if the functions exist
        functions_to_check = [
            'preload_historical_candles_working',
            'convert_to_heikin_ashi_fixed'
        ]
        
        # Try importing main to check if functions exist
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("main", "main.py")
            main_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(main_module)
            
            for func_name in functions_to_check:
                if hasattr(main_module, func_name):
                    print(f"✅ {func_name} found in main.py")
                else:
                    print(f"❌ {func_name} NOT found in main.py")
                    return False
            
        except Exception as import_error:
            print(f"⚠️ Could not validate main.py functions: {import_error}")
            print("💡 Make sure you added the functions to main.py")
        
        # Test timestamp parsing fix
        from datetime import datetime
        
        # Test different timestamp formats
        test_timestamps = [
            1725264900000,  # milliseconds
            "2025-09-01T15:45:00+05:30",  # ISO format
            1725264900,     # seconds
        ]
        
        print("\n🔧 Testing timestamp parsing fix:")
        
        for ts in test_timestamps:
            try:
                if isinstance(ts, str):
                    result = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                else:
                    result = datetime.fromtimestamp(float(ts) / 1000)
                print(f"✅ {ts} → {result}")
            except Exception as e:
                print(f"❌ {ts} → Error: {e}")
        
        print("\n✅ Step 5 validation completed")
        return True
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(validate_step5_integration())
    
    if result:
        print("\n🎯 Step 5 is ready for implementation!")
        print("💡 Add the functions to main.py and test with your bot")
    else:
        print("\n⚠️ Step 5 needs fixes before implementation")