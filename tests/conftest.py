import os


# Routine registration tests should not depend on the availability of the public
# U.S. Census Geocoder. Dedicated address-verification tests cover the live
# response parsing and the registration policy integration separately.
os.environ.setdefault("CAM_ADDRESS_VALIDATION_MODE", "stub")
