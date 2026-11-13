"""Production profile boundary; every profile uses 1=enabled permissions."""
REFERENCE_VERSIONS = ('1.5.4', '1.6.4')
CURRENT_VERSIONS = ('1.5.5', '1.6.5')
SUPPORTED_VERSIONS = REFERENCE_VERSIONS + CURRENT_VERSIONS
SUPPORTED_MODES = ('analyze', 'patch')

def require_profile(version):
    if version not in SUPPORTED_VERSIONS:
        raise ValueError('unsupported EMU1101-EXT version: choose '+', '.join(SUPPORTED_VERSIONS))

def require_mode(mode):
    if mode not in SUPPORTED_MODES:
        raise ValueError('unsupported mode: choose analyze or patch')
