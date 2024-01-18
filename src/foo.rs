use arrayref::array_ref;

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

#[derive(PartialEq, Debug)]
struct Person {
    id: i32,
    name: [char; 20],
    age: Option<i16>,
    city: Option<[char; 15]>,
    is_student: bool,
}

#[derive(PartialEq, Debug)]
struct Employee {
    employee_id: i32,
    employee_name: [char; 25],
    salary: i32,
    department: Option<[char; 20]>,
    is_manager: bool,
}

#[derive(PartialEq, Debug)]
enum Message {
    Person(Person),
    Employee(Employee),
}

impl Person {
    fn max_payload_size() -> usize {
    }

}
impl Employee {
    fn max_payload_size() -> usize {
    }

}
