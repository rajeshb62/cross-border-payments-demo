class CrossBorderAppBaseException(Exception):
    pass

class MerchantNotFoundError(CrossBorderAppBaseException):
    pass

class MerchantNotApprovedError(CrossBorderAppBaseException):
    pass

class TransactionNotFoundError(CrossBorderAppBaseException):
    pass

class FXRateUnavailableError(CrossBorderAppBaseException):
    pass

class InvalidTransactionStateError(CrossBorderAppBaseException):
    pass

class OGPSPLimitExceededError(CrossBorderAppBaseException):
    pass
