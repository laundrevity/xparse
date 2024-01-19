use std::io::Write;
use xparse::{Message, Order, Side};

fn main() {
    let message_original = Message::Order(Order {
        order_id: 123,
        price: 3.14,
        account_id: Some(123),
        quantity: 123,
        order_side: Side::Buy,
        instrument_id: 123,
        symbol: None,
    });

    println!("message_original: {:?}", message_original);

    let message_bytes = message_original.serialize();
    println!("message_bytes:");
    for byte in &message_bytes {
        print!("{:X?}", byte);
    }
    print!("\n");

    let mut file = std::fs::File::create("out.xb").unwrap();
    file.write_all(&message_bytes).unwrap();

    let data = std::fs::read("out.xb").unwrap();
    let message_read = Message::deserialize(&data).unwrap();
    println!("message_read: {:?}", message_read);
}
