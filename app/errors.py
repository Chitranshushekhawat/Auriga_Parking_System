from http import HTTPStatus


class ApiError(Exception):
    def __init__(self, message, status=HTTPStatus.BAD_REQUEST):
        self.message = message
        self.status = status
