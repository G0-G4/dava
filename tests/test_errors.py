from dava.errors import RequestError


class TestRequestError:
    def test_is_exception(self):
        assert issubclass(RequestError, Exception)

    def test_message(self):
        err = RequestError("something went wrong")
        assert str(err) == "something went wrong"

    def test_raise_and_catch(self):
        try:
            raise RequestError("test error")
        except RequestError as e:
            assert str(e) == "test error"