#[derive(Debug, PartialEq)]
enum Role {
    Employee = 1,
    Student = 2,
}

fn to_bytes(role: Role) -> [u8; 1] {
    [(role as u8)]
}

fn from_bytes(bytes: [u8; 1]) -> Option<Role> {
    match bytes[0] {
        1 => Some(Role::Employee),
        2 => Some(Role::Student),
        _ => None,
    }
}

fn main() {
    let e1 = Role::Employee;
    let e2 = Role::Student;

    // Serialize
    let bytes_e1 = to_bytes(e1);
    let bytes_e2 = to_bytes(e2);

    // Deserialize
    let deserialized_e1 = from_bytes(bytes_e1).expect("Invalid data");
    let deserialized_e2 = from_bytes(bytes_e2).expect("Invalid data");

    println!("e1: {:?}", deserialized_e1);
    println!("e2: {:?}", deserialized_e2);
}
