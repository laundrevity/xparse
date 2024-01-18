This project is a tool for generating Rust code to serialize and deserialize certain message formats as specified in XML.

<h2> Run the example </h2>

This example assumes you have Rust installed (and that `cargo` is in your PATH) and that you have Python3 installed (so that `python3` is in your PATH).

The file `example_schema.xml` contains an example of a set of message formats we could specify:
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

The Rust code can be generated via `python3 main.py`, and the tests can be run via `cargo test`.

<h2>Supported message types</h2>
Presently, only the following message attribute types are supported:

- signed integers (`int`), unsigned integers (`uint`) and floats (`float`) of byte length 1, 2, 4, 8, 16, or 128
- booleans (`bool`)
- strings (`str`) of fixed length, consisting only of ASCII characters, right-padded with spaces
- enums, with up to 256 different variants per enum

<h2>Binary message format</h2>
Every message begins with a <i>header</i>, which consists of:

- 4 byte unsigned integer <i>message length</i> (including the header length)
- 1 byte unsigned integer <i>message type</i> indicating what the message format (corresponding to `messageFormat id` in the XML)
- 4 byte unsigned integer <i>bitmask</i> bitmask which, in big endian, indicates which, if any, of the optional fields are present

After the header, the message consists of the fields in order of appearance in the XML which are indicated as present by the bitmask.