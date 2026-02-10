"""
Utility functions for sanitizing data according to MRP XSD patterns.
"""


def sanitize_forbidden_chars(value, max_length=None):
    """
    Sanitize value according to XSD pattern [^'#|\t]*.
    Removes: single quote ('), hash (#), pipe (|), tab (\t)
    
    Args:
        value: The string value (can be None)
        max_length: Optional max length to truncate
        
    Returns:
        str: Sanitized string, empty string if input is None/empty
    """
    if not value:
        return ""
    
    # Remove forbidden characters
    sanitized = str(value).replace("'", "").replace("#", "").replace("|", "").replace("\t", "")
    
    # Truncate if max_length specified
    if max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized


def sanitize_uppercase_only(value, max_length=None):
    """
    Sanitize value to uppercase only according to XSD pattern [A-Z]*.
    
    Args:
        value: The string value (can be None)
        max_length: Optional max length to truncate
        
    Returns:
        str: Uppercase string, empty string if input is None/empty
    """
    if not value:
        return ""
    
    # Convert to uppercase and remove non-letters
    sanitized = ''.join(c for c in str(value).upper() if c.isalpha())
    
    # Truncate if max_length specified
    if max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized


def sanitize_zipcode(value, max_length=15):
    """
    Sanitize zipcode according to XSD pattern [a-zA-Z0-9\. -]*.
    Allows: letters, digits, dots, spaces, hyphens
    
    Args:
        value: The zipcode string (can be None)
        max_length: Max length (default 15)
        
    Returns:
        str: Sanitized zipcode, empty string if input is None/empty
    """
    if not value:
        return ""
    
    # Keep only allowed characters
    sanitized = ''.join(c for c in str(value) if c.isalnum() or c in '. -')
    
    # Truncate
    return sanitized[:max_length]


def sanitize_city(city_value):
    """
    Sanitize city value according to XSD pattern [^'#|\t]*.
    Convenience function that calls sanitize_forbidden_chars with max_length=30.
    
    Args:
        city_value: The city string value (can be None)
        
    Returns:
        str: Sanitized city string, empty string if input is None/empty
    """
    if not city_value:
        return ""
    sanitized_city = str(city_value).replace("'", "`")
    return sanitize_forbidden_chars(sanitized_city, max_length=30)

