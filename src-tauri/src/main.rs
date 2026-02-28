// Hides the Windows console window in release builds.
// In debug builds the console is visible so log output can be read.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    almready_lib::run()
}
