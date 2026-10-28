def pytest_configure(config):
    config.addinivalue_line("markers", "slow: runs Blender and/or Unreal headless (tens of seconds)")
