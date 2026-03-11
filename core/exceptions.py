class PaymentBaseException(Exception):
    """Base for all payment system errors."""


class RateLockExpiredError(PaymentBaseException):
    """Rate lock has expired or does not exist."""


class LRSLimitExceededError(PaymentBaseException):
    """Transaction would breach the $250K/year LRS cap."""


class ComplianceError(PaymentBaseException):
    """General compliance failure (KYC, purpose code, etc.)."""


class InvalidStateMachineTransitionError(PaymentBaseException):
    """Attempted state transition is not allowed."""


class FXError(PaymentBaseException):
    """Error communicating with or executing via FX provider."""
