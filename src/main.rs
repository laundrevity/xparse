use arrayref::array_ref;

use xparse::{string_to_char_array, Employee, Header, Message, Person};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_header_serialization() {
        let header = Header {
            msg_size: 23,
            msg_type: 1,
            bitmask: 33, // Example bitmask (1 << 0 | 1 << 5)
        };

        let serialized = header.to_bytes();
        let deserialized = Header::from_bytes(&serialized);

        assert_eq!(header, deserialized);
    }

    #[test]
    fn test_header_fields() {
        let header = Header {
            msg_size: 100,
            msg_type: 2,
            bitmask: 18, // Example bitmask (1 << 1 | 1 << 4)
        };

        assert_eq!(header.msg_size, 100);
        assert_eq!(header.msg_type, 2);
        assert_eq!(header.bitmask, 18);
    }

    #[test]
    fn test_person_serialize_deserialize() {
        let message_original = Message::Person(Person {
            id: 1234,
            name: string_to_char_array("Huey Lewis").unwrap(),
            age: None,
            city: None,
            is_student: false,
        });

        let message_bytes = message_original.serialize();
        let message_result = Message::deserialize(&message_bytes).unwrap();

        assert_eq!(message_original, message_result);
    }

    #[test]
    fn test_employee_serialize_deserialize() {
        let message_original = Message::Employee(Employee {
            employee_id: 594,
            employee_name: string_to_char_array("Alice Bobstein").unwrap(),
            salary: 275000,
            department: Some(string_to_char_array("Hematology").unwrap()),
            is_manager: true,
        });

        let message_bytes = message_original.serialize();
        let message_result = Message::deserialize(&message_bytes).unwrap();

        assert_eq!(message_original, message_result);
    }
}

fn main() {
    println!("yoloswag420");
}
