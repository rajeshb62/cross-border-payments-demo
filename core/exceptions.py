class EximPeBaseException(Exception):
    pass

class MerchantNotFoundError(EximPeBaseException):
    pass

class MerchantNotApprovedError(EximPeBaseException):
    pass

class TransactionNotFoundError(EximPeBaseException):
    pass

class FXRateUnavailableError(EximPeBaseException):
    pass

class InvalidTransactionStateError(EximPeBaseException):
    pass

class OGPSPLimitExceededError(EximPeBaseException):
    pass
