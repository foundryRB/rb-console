class OperationUnknown(RuntimeError):
    """Dispatch may have taken effect; authoritative resolution is required."""

    def __init__(self, operation_key: str, reason: str = ""):
        self.operation_key = operation_key
        self.reason = reason
        failed = f" (its dispatch failed: {reason})" if reason else ""
        super().__init__(f"The operation outcome is unknown{failed}; inspect its receipt before retrying.")
