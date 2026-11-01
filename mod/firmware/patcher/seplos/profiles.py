"""Production profile boundary; permission polarity is fixed by each profile."""
SUPPORTED_VERSIONS = ('1.5.4', '1.6.4')
SUPPORTED_MODES = ('analyze', 'patch')

def require_profile(version):
    if version not in SUPPORTED_VERSIONS:
        raise ValueError('unsupported MAINT version: choose 1.5.4 or 1.6.4')

def require_mode(mode):
    if mode not in SUPPORTED_MODES:
        raise ValueError('unsupported mode: choose analyze or patch')
