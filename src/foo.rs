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

impl Person {
    fn max_payload_size() -> usize {
		42
    }

	fn serialize(&self) -> Vec<u8> {
		let mut buf: Vec<u8> = Vec::with_capacity(Person::max_payload_size());

		buf.extend_from_slice(&self.id.to_be_bytes());

		buf.append(self.name.iter().map(|&c| c as u8).collect::<Vec<u8>>().as_mut());

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

		let header = Header::from_bytes(array_ref![buffer, 0, 9]);
		let mut offset = 9;

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
		54
    }

	fn serialize(&self) -> Vec<u8> {
		let mut buf: Vec<u8> = Vec::with_capacity(Employee::max_payload_size());

		buf.extend_from_slice(&self.employee_id.to_be_bytes());

		buf.append(self.employee_name.iter().map(|&c| c as u8).collect::<Vec<u8>>().as_mut());

		buf.extend_from_slice(&self.salary.to_be_bytes());

		match self.department {
			Some(department) => buf.append(department.iter().map(|&c| c as u8).collect::<Vec<u8>>().as_mut()),
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

	fn deserialize(buffer: &[u8]) -> Result<Self, &'static str> {
		if buffer.len() < 9 {
			return Err("Buffer too short for header");
		}

		let header = Header::from_bytes(array_ref![buffer, 0, 9]);
		let mut offset = 9;

	}

}

#[derive(PartialEq, Debug)]
enum Message {
    Person(Person),
    Employee(Employee),
}

