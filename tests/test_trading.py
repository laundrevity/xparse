from xparse import PyMessage


def test_order():
    message_bytes = open(f"order.xb", "rb").read()
    message = PyMessage(message_bytes)
    message_bytes_out = message.to_bytes()

    for x, y in zip(message_bytes, message_bytes_out):
        assert x == y
