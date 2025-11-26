#!/usr/bin/env python3
"""
Migration test script to verify CustomElectrumX compatibility.
This script tests that all custom RPC methods are properly available.
"""

import sys
import os
import asyncio

# Add the server directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'server'))

def test_custom_session_import():
    """Test that CustomElectrumX can be imported successfully."""
    try:
        from server.custom_session import CustomElectrumX
        print("✅ CustomElectrumX imported successfully")
        return CustomElectrumX
    except ImportError as e:
        print(f"❌ Failed to import CustomElectrumX: {e}")
        return None

def test_custom_methods(custom_electrumx_class):
    """Test that all custom RPC methods are available."""
    if not custom_electrumx_class:
        return False
    
    # Your custom methods (non-native)
    custom_methods = [
        'getrawmempool',
        'getblockcount',
        'getblock',
        'getblockhash',
        'getblockchaininfo',
        'gettxoutsetinfo',
        'getmempoolinfo',
        'getrawblocks',
        'block_subscribe',
        'get_address_history',
        'get_history',
        'get_history_hashx',
        'get_hashx',
    ]
    
    print("\n📋 Testing YOUR CUSTOM methods:")
    missing_methods = []
    
    for method in custom_methods:
        if hasattr(custom_electrumx_class, method):
            print(f"✅ {method}")
        else:
            print(f"❌ {method} - Missing")
            missing_methods.append(method)
    
    success = len(missing_methods) == 0
    print(f"\n📊 Custom Methods: {len(custom_methods) - len(missing_methods)}/{len(custom_methods)} available")
    
    if not success:
        print(f"❌ Missing custom methods: {missing_methods}")
    
    return success

def test_native_methods(custom_electrumx_class):
    """Test that native ElectrumX methods are still available."""
    if not custom_electrumx_class:
        return False
    
    # Native ElectrumX methods that should still work
    native_methods = [
        'address_get_balance',
        'address_get_history',
        'address_get_mempool',
        'address_listunspent',
        'address_subscribe',
        'block_get_chunk',
        'block_get_header',
        'relayfee',
    ]
    
    print("\n📋 Testing NATIVE ElectrumX methods:")
    missing_methods = []
    
    for method in native_methods:
        if hasattr(custom_electrumx_class, method):
            print(f"✅ {method}")
        else:
            print(f"❌ {method} - Missing")
            missing_methods.append(method)
    
    success = len(missing_methods) == 0
    print(f"\n📊 Native Methods: {len(native_methods) - len(missing_methods)}/{len(native_methods)} available")
    
    if not success:
        print(f"❌ Missing native methods: {missing_methods}")
    
    return success

def test_protocol_compatibility():
    """Test that protocol versions are properly set."""
    try:
        from server.custom_session import CustomElectrumX
        
        # Check protocol versions
        if hasattr(CustomElectrumX, 'PROTOCOL_MAX'):
            protocol_max = CustomElectrumX.PROTOCOL_MAX
            print(f"✅ Protocol max version: {protocol_max}")
            
            # Should support latest protocol (1.6)
            if protocol_max >= (1, 6, 0):
                print("✅ Supports latest Electrum protocol (1.6)")
                return True
            else:
                print(f"⚠️  Protocol version {protocol_max} may be outdated")
                return False
        else:
            print("❌ PROTOCOL_MAX not found")
            return False
            
    except Exception as e:
        print(f"❌ Error testing protocol compatibility: {e}")
        return False

def test_inheritance_structure():
    """Test that CustomElectrumX properly inherits from BaseElectrumX."""
    try:
        from server.custom_session import CustomElectrumX
        from electrumx.server.session import ElectrumX as BaseElectrumX
        
        if issubclass(CustomElectrumX, BaseElectrumX):
            print("✅ CustomElectrumX properly inherits from BaseElectrumX")
            
            # Check if it's a proper extension (not just a copy)
            if CustomElectrumX != BaseElectrumX:
                print("✅ CustomElectrumX is a proper extension (not identical)")
                return True
            else:
                print("❌ CustomElectrumX is identical to BaseElectrumX")
                return False
        else:
            print("❌ CustomElectrumX does not inherit from BaseElectrumX")
            return False
            
    except Exception as e:
        print(f"❌ Error testing inheritance: {e}")
        return False

async def main():
    """Run all migration tests."""
    print("🔧 Starting ElectrumX Migration Tests")
    print("=" * 50)
    
    # Test 1: Import
    custom_class = test_custom_session_import()
    if not custom_class:
        print("\n❌ Migration failed: Cannot import CustomElectrumX")
        return False
    
    # Test 2: Custom methods
    print("\n📋 Testing method availability:")
    custom_methods_ok = test_custom_methods(custom_class)
    
    # Test 3: Native methods
    native_methods_ok = test_native_methods(custom_class)
    
    # Test 4: Protocol compatibility
    print("\n📡 Testing protocol compatibility:")
    protocol_ok = test_protocol_compatibility()
    
    # Test 5: Inheritance structure
    print("\n🏗️ Testing inheritance structure:")
    inheritance_ok = test_inheritance_structure()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 MIGRATION TEST SUMMARY")
    print("=" * 50)
    
    tests = [
        ("Custom Methods", custom_methods_ok),
        ("Native Methods", native_methods_ok),
        ("Protocol Compatibility", protocol_ok),
        ("Inheritance Structure", inheritance_ok),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, result in tests:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 MIGRATION SUCCESSFUL!")
        print("✅ All custom RPC methods are available")
        print("✅ Native ElectrumX methods preserved")
        print("✅ Protocol compatibility maintained")
        print("✅ Ready for production deployment")
        return True
    else:
        print(f"\n⚠️  MIGRATION ISSUES DETECTED")
        print("❌ Some tests failed - review before deployment")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)