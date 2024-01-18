use arrayref::array_ref;

mod foo;

fn string_to_char_array<const N: usize>(s: &str) -> Result<[char; N], &'static str> {
    if s.len() > N {
        return Err("String is too long");
    }

    let mut char_vec: Vec<char> = s.chars().collect();
    while char_vec.len() < N {
        char_vec.push(' '); // Fill the remaining spaces with a default character
    }

    // Attempt to convert Vec<char> into [char; N]
    let char_array: [char; N] = char_vec
        .try_into()
        .map_err(|_| "Failed to convert to array")?;
    Ok(char_array)
}

#[derive(PartialEq, Debug)]
struct Person {
    id: i32,
    name: [char; 20],
    age: Option<i16>,
    city: Option<[char; 15]>,
    is_student: bool,
}

impl Person {
    fn max_payload_size() -> usize {
        4 + 20 + 2 + 15 + 1
    }

    fn serialize(&self) -> Vec<u8> {
        let mut buf: Vec<u8> = Vec::with_capacity(Person::max_payload_size());

        buf.extend_from_slice(&self.id.to_be_bytes());

        buf.append(
            self.name
                .iter()
                .map(|&c| c as u8)
                .collect::<Vec<u8>>()
                .as_mut(),
        );

        match self.age {
            Some(age) => buf.extend_from_slice(&age.to_be_bytes()),
            _ => {}
        }

        match self.city {
            Some(city) => buf.append(city.iter().map(|&c| c as u8).collect::<Vec<u8>>().as_mut()),
            _ => {}
        }

        buf.push(if self.is_student { 1 } else { 0 });

        buf
    }

    fn get_bitmask(&self) -> u32 {
        let mut mask: u32 = 0;

        match self.age {
            Some(_) => mask |= 1 << 0,
            _ => {}
        }

        match self.city {
            Some(_) => mask |= 1 << 1,
            _ => {}
        }

        mask
    }

    fn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {
        if buffer.len() < 9 {
            return Err("Buffer too short for header");
        }

        // Extract and interpret the header
        let header = Header::from_bytes(array_ref![buffer, 0, 9]);
        let mut offset = 9; // Start reading data after the header

        let id = i32::from_be_bytes(
            buffer[offset..offset + 4]
                .try_into()
                .map_err(|_| "Invalid buffer: id")?,
        );
        offset += 4;

        let mut name = [' '; 20];
        for i in 0..20 {
            name[i] = buffer[offset + i] as char;
        }
        offset += 20;

        let age = if header.bitmask & (1 << 0) != 0 {
            let age_value = i16::from_be_bytes(
                buffer[offset..offset + 2]
                    .try_into()
                    .map_err(|_| "Invalid buffer: age")?,
            );
            offset += 2;
            Some(age_value)
        } else {
            None
        };

        let city = if header.bitmask & (1 << 1) != 0 {
            let mut city_chars = [' '; 15];
            for i in 0..15 {
                city_chars[i] = buffer[offset + i] as char;
            }
            offset += 15;
            Some(city_chars)
        } else {
            None
        };

        let is_student = buffer[offset] != 0;

        Ok(Self {
            id,
            name,
            age,
            city,
            is_student,
        })
    }
}

#[derive(PartialEq, Debug)]
struct Employee {
    employee_id: i32,
    employee_name: [char; 25],
    salary: i32,
    department: Option<[char; 20]>,
    is_manager: bool,
}

impl Employee {
    fn max_payload_size() -> usize {
        4 + 25 + 4 + 20 + 1
    }

    fn serialize(&self) -> Vec<u8> {
        let mut buf: Vec<u8> = Vec::with_capacity(Employee::max_payload_size());

        buf.extend_from_slice(&self.employee_id.to_be_bytes());

        buf.append(
            self.employee_name
                .iter()
                .map(|&c| c as u8)
                .collect::<Vec<u8>>()
                .as_mut(),
        );

        buf.extend_from_slice(&self.salary.to_be_bytes());

        match self.department {
            Some(department) => buf.append(
                department
                    .iter()
                    .map(|&c| c as u8)
                    .collect::<Vec<u8>>()
                    .as_mut(),
            ),
            _ => {}
        }

        buf.push(if self.is_manager { 1 } else { 0 });

        buf
    }

    fn get_bitmask(&self) -> u32 {
        let mut mask: u32 = 0;

        match self.department {
            Some(_) => mask |= 1 << 0,
            _ => {}
        }

        mask
    }

    // Optional: Deserialize method for Employee
    fn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {
        if buffer.len() < 9 {
            return Err("Buffer too short for header");
        }

        // Extract and interpret the header
        let header = Header::from_bytes(array_ref![buffer, 0, 9]);
        let mut offset = 9; // Start reading data after the header

        let employee_id = i32::from_be_bytes(
            buffer[offset..offset + 4]
                .try_into()
                .map_err(|_| "Invalid buffer: employee_id")?,
        );
        offset += 4;

        let mut employee_name = [' '; 25];
        for i in 0..25 {
            employee_name[i] = buffer[offset + i] as char;
        }
        offset += 25;

        let salary = i32::from_be_bytes(
            buffer[offset..offset + 4]
                .try_into()
                .map_err(|_| "Invalid buffer: salary")?,
        );
        offset += 4;

        let department = if header.bitmask & (1 << 0) != 0 {
            let mut department_chars = [' '; 20];
            for i in 0..20 {
                department_chars[i] = buffer[offset + i] as char;
            }
            offset += 20;
            Some(department_chars)
        } else {
            None
        };

        let is_manager = buffer[offset] != 0;

        Ok(Self {
            employee_id,
            employee_name,
            salary,
            department,
            is_manager,
        })
    }
}

#[derive(PartialEq, Debug)]
enum Message {
    Person(Person),
    Employee(Employee),
}

impl Message {
    fn serialize(&self) -> Vec<u8> {
        let mut buffer = match self {
            Message::Person(p) => p.serialize(),
            Message::Employee(e) => e.serialize(),
        };

        // Create a header and prepend it to the buffer
        let header = Header {
            msg_size: buffer.len() as u32 + 9, // +9 for header size
            msg_type: match self {
                Message::Person(_) => 1,
                Message::Employee(_) => 2,
            },
            bitmask: self.get_bitmask(), // Define how to set bitmask
        };

        let mut header_bytes = header.to_bytes().to_vec();
        header_bytes.append(&mut buffer);
        header_bytes
    }

    fn get_bitmask(&self) -> u32 {
        match self {
            Message::Person(p) => p.get_bitmask(),
            Message::Employee(p) => p.get_bitmask(),
        }
    }

    fn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {
        match buffer[4] {
            1 => match Person::deserialize(buffer) {
                Ok(person) => Ok(Message::Person(person)),
                Err(e) => Err(e),
            },
            2 => match Employee::deserialize(buffer) {
                Ok(employee) => Ok(Message::Employee(employee)),
                Err(e) => Err(e),
            },
            _ => Err("Unknown message type id"),
        }
    }
}

#[derive(Debug, PartialEq)]
struct Header {
    msg_size: u32,
    msg_type: u8,
    bitmask: u32,
}

impl Header {
    fn to_bytes(&self) -> [u8; 9] {
        let size_bytes = self.msg_size.to_be_bytes();
        let mask_bytes = self.bitmask.to_be_bytes();

        [
            size_bytes[0],
            size_bytes[1],
            size_bytes[2],
            size_bytes[3],
            self.msg_type,
            mask_bytes[0],
            mask_bytes[1],
            mask_bytes[2],
            mask_bytes[3],
        ]
    }

    fn from_bytes(buffer: &[u8; 9]) -> Self {
        let msg_size = u32::from_be_bytes([buffer[0], buffer[1], buffer[2], buffer[3]]);
        let msg_type = buffer[4];
        let bitmask = u32::from_be_bytes([buffer[5], buffer[6], buffer[7], buffer[8]]);

        Self {
            msg_size,
            msg_type,
            bitmask,
        }
    }
}

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
