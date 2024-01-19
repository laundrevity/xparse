This project is a tool for generating Rust code and Python bindings for serializing and deserializing certain message formats as specified in XML.

<h2> Run the example </h2>

This example assumes you have Rust installed (so that `cargo` is in your PATH) and that you have Python3 installed (so that `python3` is in your PATH).

The folder `example_schemas` contains some examples of sets of message formats we could specify, e.g. `school.xml`
```xml
<root>
    <enumTypes>
        <enumType name="role">
            <enumValue name="employee" value="1"/>
            <enumValue name="student" value="2"/>
        </enumType>
    </enumTypes>
    <messageFormats>
        <messageFormat id="1" name="person">
            <attribute name="id" type="int" length="4" required="true"/>
            <attribute name="name" type="str" length="20" required="true"/>
            <attribute name="age" type="uint" length="2" required="false"/>
            <attribute name="city" type="str" length="15" required="false"/>
            <attribute name="is_student" type="bool" length="1" required="true"/>
            <attribute name="person_role" type="role" required="false"/> 
        </messageFormat>

        <messageFormat id="2" name="employee">
            <attribute name="employee_id" type="int" length="4" required="true"/>
            <attribute name="employee_name" type="str" length="25" required="true"/>
            <attribute name="salary" type="uint" length="4" required="true"/>
            <attribute name="department" type="str" length="20" required="false"/>
            <attribute name="is_manager" type="bool" length="1" required="true"/>
        </messageFormat>

        <messageFormat id="3" name="student">
            <attribute name="person_id" type="int" length="4" required="true"/>
            <attribute name="zip_code" type="uint" length="4" required="true"/>
            <attribute name="major" type="str" length="20" required="false"/>
            <attribute name="gpa" type="float" length="4" required="true"/>
            <attribute name="gpa_in_major" type="float" length="4" required="false"/>
        </messageFormat>
    </messageFormats>
</root>
```
which generates (passing) Python tests
```python
from xparse import PyMessage


def test_person_deserialize_serialize():
	message_bytes = open("school_person.xb", "rb").read()
	message = PyMessage.from_bytes(message_bytes)
	message_bytes_out = message.to_bytes()

	for x, y in zip(message_bytes, message_bytes_out):
		assert x == y


def test_person_serialize_deserialize():
	person = PyMessage.person(
		id=-123,
		name='John Doe',
		age=123,
		city='John Doe',
		is_student=True,
		person_role=1,
	)
	person_bytes = person.to_bytes()
	person_result = PyMessage.from_bytes(person_bytes)

	assert person == person_result


def test_employee_deserialize_serialize():
	message_bytes = open("school_employee.xb", "rb").read()
	message = PyMessage.from_bytes(message_bytes)
	message_bytes_out = message.to_bytes()

	for x, y in zip(message_bytes, message_bytes_out):
		assert x == y


def test_employee_serialize_deserialize():
	employee = PyMessage.employee(
		employee_id=-123,
		employee_name='John Doe',
		salary=123,
		department='John Doe',
		is_manager=True,
	)
	employee_bytes = employee.to_bytes()
	employee_result = PyMessage.from_bytes(employee_bytes)

	assert employee == employee_result


def test_student_deserialize_serialize():
	message_bytes = open("school_student.xb", "rb").read()
	message = PyMessage.from_bytes(message_bytes)
	message_bytes_out = message.to_bytes()

	for x, y in zip(message_bytes, message_bytes_out):
		assert x == y


def test_student_serialize_deserialize():
	student = PyMessage.student(
		person_id=-123,
		zip_code=123,
		major='John Doe',
		gpa=3.14,
		gpa_in_major=3.14,
	)
	student_bytes = student.to_bytes()
	student_result = PyMessage.from_bytes(student_bytes)

	assert student == student_result
```

or `trading.xml`
```xml
<root>
    <enumTypes>
        <enumType name="side">
            <enumValue name="buy" value="1"/>
            <enumValue name="sell" value="2"/>
        </enumType>
    </enumTypes>
    <messageFormats>
        <messageFormat id="1" name="order">
            <attribute name="order_id" type="uint" length="8" required="true"/>
            <attribute name="price" type="float" length="8" required="true"/>
            <attribute name="account_id" type="uint" length="4" required="false"/>
            <attribute name="quantity" type="uint" length="8" required="true"/>
            <attribute name="order_side" type="side" required="true"/>
            <attribute name="instrument_id" type="uint" length="8" required="true"/>
            <attribute name="symbol" type="str" length="20" required="false"/>
        </messageFormat>
        <messageFormat id="2" name="position">
            <attribute name="quantity" type="int" length="8" required="true"/>
            <attribute name="account_id" type="uint" length="4" required="false"/>
            <attribute name="instrument_id" type="uint" length="8" required="true"/>
            <attribute name="symbol" type="str" length="20" required="false"/>
        </messageFormat>
    </messageFormats>
</root>
```

which generates (passing) Python tests
```python
from xparse import PyMessage


def test_order_deserialize_serialize():
	message_bytes = open("trading_order.xb", "rb").read()
	message = PyMessage.from_bytes(message_bytes)
	message_bytes_out = message.to_bytes()

	for x, y in zip(message_bytes, message_bytes_out):
		assert x == y


def test_order_serialize_deserialize():
	order = PyMessage.order(
		order_id=123,
		price=3.14,
		account_id=123,
		quantity=123,
		order_side=1,
		instrument_id=123,
		symbol='John Doe',
	)
	order_bytes = order.to_bytes()
	order_result = PyMessage.from_bytes(order_bytes)

	assert order == order_result


def test_position_deserialize_serialize():
	message_bytes = open("trading_position.xb", "rb").read()
	message = PyMessage.from_bytes(message_bytes)
	message_bytes_out = message.to_bytes()

	for x, y in zip(message_bytes, message_bytes_out):
		assert x == y


def test_position_serialize_deserialize():
	position = PyMessage.position(
		quantity=-123,
		account_id=123,
		instrument_id=123,
		symbol='John Doe',
	)
	position_bytes = position.to_bytes()
	position_result = PyMessage.from_bytes(position_bytes)

	assert position == position_result
```

To generate Rust code and Python bindings and run all tests for the `trading.xml` example schema:
```shell
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py example_schemas/trading.xml
maturin develop
cargo test
cargo run
pytest
``` 

<h2>Supported message types</h2>
Presently, only the following message attribute types are supported:

- signed integers (`int`), unsigned integers (`uint`) and floats (`float`) of byte length 1, 2, 4, 8, 16, or 128
- booleans (`bool`)
- strings (`str`) of fixed length, consisting only of ASCII characters, right-padded with spaces
- enums, with up to 256 different variants per enum

<h2>Binary message format</h2>
Every message begins with a <i>header</i>, which consists of:

- 4 byte unsigned integer <i>message length</i> (including the fixed header length, 9)
- 1 byte unsigned integer <i>message type</i> indicating the message format (corresponding to `messageFormat id` in the XML)
- 4 byte unsigned integer <i>bitmask</i> which, in big endian, indicates which, if any, of the optional fields are present

After the header, the message consists of the fields in order of appearance in the XML which are indicated as present by the bitmask.