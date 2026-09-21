class CustomException(Exception):
    """
    自定义异常基类
    custom exception base class
    """

    def __init__(
        self,
        code: int | None = None,
        msg: str | None = None,
    ) -> None:
        """
        - code (int): error code. 业务状态码。
        - msg (str): error message. 错误消息。
        """
        super().__init__(msg)
        self.code = code
        self.msg = msg

    def __str__(self) -> str | None:
        """
        return error message
        """
        return self.msg
