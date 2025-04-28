import lgpio
import time

# Open GPIO chip
chip = lgpio.gpiochip_open(0)  # Open /dev/gpiochip0

# GPIO setup for buzzer
BUZZER_PIN = 27  # GPIO27 for buzzer control
lgpio.gpio_claim_output(chip, BUZZER_PIN)  # Set as output

# Define note frequencies (in Hz, based on standard pitches.h)
REST = 0
NOTE_G4 = 392
NOTE_A4 = 440
NOTE_AS4 = 466
NOTE_B4 = 494
NOTE_C5 = 523
NOTE_D5 = 587
NOTE_DS5 = 622
NOTE_E5 = 659
NOTE_F5 = 698
NOTE_FS5 = 740
NOTE_G5 = 784
NOTE_GS4 = 415
NOTE_A5 = 880
NOTE_E4 = 329
NOTE_G4 = 392
NOTE_C4 = 261
NOTE_D4 = 293

# Define song melodies and durations
RICK_ROLL = [
    (NOTE_A4, 8), (REST, 8), (NOTE_B4, 8), (REST, 8), (NOTE_C5, 8), (REST, 8), (NOTE_A4, 8), (REST, 4),
    (NOTE_D5, 8), (REST, 8), (NOTE_E5, 8), (REST, 8), (NOTE_D5, 2), (REST, 2),
    (NOTE_G4, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_E5, 2), (NOTE_E5, 8), (REST, 8),
    (NOTE_D5, 2), (REST, 8),
    (NOTE_G4, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_D5, 2), (NOTE_D5, 8), (REST, 8),
    (NOTE_C5, 4), (REST, 8), (NOTE_B4, 8), (NOTE_A4, 8), (REST, 8),
    (NOTE_G4, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_C5, 2), (NOTE_D5, 8), (REST, 8),
    (NOTE_B4, 2), (NOTE_A4, 8), (NOTE_G4, 4), (REST, 8), (NOTE_G4, 8), (REST, 8), (NOTE_D5, 8), (REST, 8), (NOTE_C5, 1), (REST, 4),
    (NOTE_G4, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_E5, 2), (NOTE_E5, 8), (REST, 8),
    (NOTE_D5, 2), (REST, 8),
    (NOTE_G4, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_G5, 2), (NOTE_B4, 8), (REST, 8),
    (NOTE_C5, 2), (REST, 8), (NOTE_B4, 8), (NOTE_A4, 8), (REST, 8),
    (NOTE_G4, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_C5, 2), (NOTE_D5, 8), (REST, 8),
    (NOTE_B4, 4), (NOTE_A4, 8), (NOTE_G4, 3), (REST, 8), (NOTE_G4, 8), (REST, 8), (NOTE_D5, 8), (REST, 8), (NOTE_C5, 1), (REST, 4),
    (NOTE_C5, 2), (REST, 6), (NOTE_D5, 2), (REST, 6), (NOTE_G4, 4), (REST, 4), (NOTE_D5, 2), (REST, 6), (NOTE_E5, 2), (REST, 3),
    (NOTE_G5, 8), (NOTE_F5, 8), (NOTE_E5, 8), (REST, 8),
    (NOTE_C5, 2), (REST, 6), (NOTE_D5, 2), (REST, 6), (NOTE_G4, 2), (REST, 1)
]

HES_A_PIRATE = [
    (NOTE_E4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (NOTE_A4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_B4, 8), (NOTE_C5, 4), (NOTE_C5, 8), (REST, 8),
    (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4), (NOTE_B4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_E4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (NOTE_A4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_B4, 8), (NOTE_C5, 4), (NOTE_C5, 8), (REST, 8),
    (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4), (NOTE_B4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_E4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (NOTE_A4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_D5, 4), (NOTE_D5, 8), (REST, 8),
    (NOTE_D5, 8), (NOTE_E5, 8), (NOTE_F5, 4), (NOTE_F5, 8), (REST, 8),
    (NOTE_E5, 8), (NOTE_D5, 8), (NOTE_E5, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_A4, 8), (NOTE_B4, 8), (NOTE_C5, 4), (NOTE_C5, 8), (REST, 8),
    (NOTE_D5, 4), (NOTE_E5, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_B4, 4), (NOTE_B4, 8), (REST, 8),
    (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_B4, 4), (REST, 4),
    (NOTE_A4, 4), (NOTE_A4, 8),
    (NOTE_A4, 8), (NOTE_B4, 8), (NOTE_C5, 4), (NOTE_C5, 8), (REST, 8),
    (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4), (NOTE_B4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_E4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (NOTE_A4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_B4, 8), (NOTE_C5, 4), (NOTE_C5, 8), (REST, 8),
    (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4), (NOTE_B4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_E4, 8), (NOTE_G4, 8), (NOTE_A4, 4), (NOTE_A4, 8), (REST, 8),
    (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_D5, 4), (NOTE_D5, 8), (REST, 8),
    (NOTE_D5, 8), (NOTE_E5, 8), (NOTE_F5, 4), (NOTE_F5, 8), (REST, 8),
    (NOTE_E5, 8), (NOTE_D5, 8), (NOTE_E5, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_A4, 8), (NOTE_B4, 8), (NOTE_C5, 4), (NOTE_C5, 8), (REST, 8),
    (NOTE_D5, 4), (NOTE_E5, 8), (NOTE_A4, 4), (REST, 8),
    (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_B4, 4), (NOTE_B4, 8), (REST, 8),
    (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_B4, 4), (REST, 4),
    (NOTE_E5, 4), (REST, 8), (REST, 4), (NOTE_F5, 4), (REST, 8), (REST, 4),
    (NOTE_E5, 8), (NOTE_E5, 8), (REST, 8), (NOTE_G5, 8), (REST, 8), (NOTE_E5, 8), (NOTE_D5, 8), (REST, 8), (REST, 4),
    (NOTE_D5, 4), (REST, 8), (REST, 4), (NOTE_C5, 4), (REST, 8), (REST, 4),
    (NOTE_B4, 8), (NOTE_C5, 8), (REST, 8), (NOTE_B4, 8), (REST, 8), (NOTE_A4, 2),
    (NOTE_E5, 4), (REST, 8), (REST, 4), (NOTE_F5, 4), (REST, 8), (REST, 4),
    (NOTE_E5, 8), (NOTE_E5, 8), (REST, 8), (NOTE_G5, 8), (REST, 8), (NOTE_E5, 8), (NOTE_D5, 8), (REST, 8), (REST, 4),
    (NOTE_D5, 4), (REST, 8), (REST, 4), (NOTE_C5, 4), (REST, 8), (REST, 4),
    (NOTE_B4, 8), (NOTE_C5, 8), (REST, 8), (NOTE_B4, 8), (REST, 8), (NOTE_A4, 2)
]

SUPER_MARIO = [
    (NOTE_E5, 8), (NOTE_E5, 8), (REST, 8), (NOTE_E5, 8), (REST, 8), (NOTE_C5, 8), (NOTE_E5, 8),
    (NOTE_G5, 4), (REST, 4), (NOTE_G4, 8), (REST, 4),
    (NOTE_C5, 4), (NOTE_G4, 8), (REST, 4), (NOTE_E4, 4),
    (NOTE_A4, 4), (NOTE_B4, 4), (NOTE_AS4, 8), (NOTE_A4, 4),
    (NOTE_G4, 8), (NOTE_E5, 8), (NOTE_G5, 8), (NOTE_A5, 4), (NOTE_F5, 8), (NOTE_G5, 8),
    (REST, 8), (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4),
    (NOTE_C5, 4), (NOTE_G4, 8), (REST, 4), (NOTE_E4, 4),
    (NOTE_A4, 4), (NOTE_B4, 4), (NOTE_AS4, 8), (NOTE_A4, 4),
    (NOTE_G4, 8), (NOTE_E5, 8), (NOTE_G5, 8), (NOTE_A5, 4), (NOTE_F5, 8), (NOTE_G5, 8),
    (REST, 8), (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4),
    (REST, 4), (NOTE_G5, 8), (NOTE_FS5, 8), (NOTE_F5, 8), (NOTE_DS5, 4), (NOTE_E5, 8),
    (REST, 8), (NOTE_GS4, 8), (NOTE_A4, 8), (NOTE_C4, 8), (REST, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_D5, 8),
    (REST, 4), (NOTE_DS5, 4), (REST, 4), (NOTE_D5, 4),
    (NOTE_C5, 2), (REST, 2),
    (REST, 4), (NOTE_G5, 8), (NOTE_FS5, 8), (NOTE_F5, 8), (NOTE_DS5, 4), (NOTE_E5, 8),
    (REST, 8), (NOTE_GS4, 8), (NOTE_A4, 8), (NOTE_C4, 8), (REST, 8), (NOTE_A4, 8), (NOTE_C5, 8), (NOTE_D5, 8),
    (REST, 4), (NOTE_DS5, 4), (REST, 4), (NOTE_D5, 4),
    (NOTE_C5, 2), (REST, 2),
    (NOTE_C5, 8), (NOTE_C5, 8), (NOTE_C5, 4), (REST, 8), (NOTE_C5, 8), (NOTE_D5, 8),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_G4, 2),
    (NOTE_C5, 8), (NOTE_C5, 8), (NOTE_C5, 4), (REST, 8), (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_E5, 8),
    (REST, 1),
    (NOTE_C5, 8), (NOTE_C5, 8), (NOTE_C5, 4), (REST, 8), (NOTE_C5, 8), (NOTE_D5, 8),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_G4, 2),
    (NOTE_E5, 8), (NOTE_E5, 8), (REST, 8), (NOTE_E5, 8), (REST, 8), (NOTE_C5, 8), (NOTE_E5, 8),
    (NOTE_G5, 4), (REST, 4), (NOTE_G4, 8), (REST, 4),
    (NOTE_C5, 4), (NOTE_G4, 8), (REST, 4), (NOTE_E4, 4),
    (NOTE_A4, 4), (NOTE_B4, 4), (NOTE_AS4, 8), (NOTE_A4, 4),
    (NOTE_G4, 8), (NOTE_E5, 8), (NOTE_G5, 8), (NOTE_A5, 4), (NOTE_F5, 8), (NOTE_G5, 8),
    (REST, 8), (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4),
    (NOTE_C5, 4), (NOTE_G4, 8), (REST, 4), (NOTE_E4, 4),
    (NOTE_A4, 4), (NOTE_B4, 4), (NOTE_AS4, 8), (NOTE_A4, 4),
    (NOTE_G4, 8), (NOTE_E5, 8), (NOTE_G5, 8), (NOTE_A5, 4), (NOTE_F5, 8), (NOTE_G5, 8),
    (REST, 8), (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_D5, 8), (NOTE_B4, 4),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_G4, 4), (REST, 4), (NOTE_GS4, 4),
    (NOTE_A4, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_A4, 2),
    (NOTE_D5, 8), (NOTE_A5, 8), (NOTE_A5, 8), (NOTE_A5, 8), (NOTE_G5, 8), (NOTE_F5, 8),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_G4, 2),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_G4, 4), (REST, 4), (NOTE_GS4, 4),
    (NOTE_A4, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_A4, 2),
    (NOTE_B4, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_E5, 8), (NOTE_D5, 8),
    (NOTE_C5, 8), (NOTE_E4, 8), (NOTE_E4, 8), (NOTE_C4, 2),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_G4, 4), (REST, 4), (NOTE_GS4, 4),
    (NOTE_A4, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_A4, 2),
    (NOTE_D5, 8), (NOTE_A5, 8), (NOTE_A5, 8), (NOTE_A5, 8), (NOTE_G5, 8), (NOTE_F5, 8),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_A4, 8), (NOTE_G4, 2),
    (NOTE_E5, 8), (NOTE_C5, 8), (NOTE_G4, 4), (REST, 4), (NOTE_GS4, 4),
    (NOTE_A4, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_A4, 2),
    (NOTE_B4, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_F5, 8), (NOTE_E5, 8), (NOTE_D5, 8),
    (NOTE_C5, 8), (NOTE_E4, 8), (NOTE_E4, 8), (NOTE_C4, 2),
    # Game over sound
    (NOTE_C5, 4), (NOTE_G4, 4), (NOTE_E4, 4),
    (NOTE_A4, 8), (NOTE_B4, 8), (NOTE_A4, 8), (NOTE_GS4, 8), (NOTE_AS4, 8), (NOTE_GS4, 8),
    (NOTE_G4, 8), (NOTE_D4, 8), (NOTE_E4, 2)
]

# Function to play a note using square wave (since PWM is not directly supported in lgpio)
def play_note(frequency, duration):
    if frequency == 0:  # Rest
        time.sleep(duration)
        return
    # Calculate period in seconds (1/frequency)
    period = 1.0 / frequency
    half_period = period / 2
    # Play a square wave for the duration
    end_time = time.time() + duration
    while time.time() < end_time:
        lgpio.gpio_write(chip, BUZZER_PIN, 1)  # HIGH
        time.sleep(half_period)
        lgpio.gpio_write(chip, BUZZER_PIN, 0)  # LOW
        time.sleep(half_period)

# Function to play a song
def play_song(song):
    for note, note_type in song:
        # Convert note type to duration in seconds (e.g., 8 = eighth note = 1000/8 ms)
        duration = 1.0 / note_type
        play_note(note, duration)
        # Pause between notes (30% of note duration)
        pause = duration * 1.30
        time.sleep(pause)

# CLI Menu
def main():
    while True:
        print("\nBuzzer Test")
        print("1. Test Buzzer")
        print("2. Exit the Test")
        choice = input("Select an option (1 or 2): ")

        if choice == "1":
            print("\nSelect a Music")
            print("1. Rick Roll")
            print("2. Hes a Pirate")
            print("3. Super Mario")
            music_choice = input("Enter your choice (1, 2, or 3): ")

            if music_choice == "1":
                print("Music Play: Rick Roll")
                play_song(RICK_ROLL)
            elif music_choice == "2":
                print("Music Play: Hes a Pirate")
                play_song(HES_A_PIRATE)
            elif music_choice == "3":
                print("Music Play: Super Mario")
                play_song(SUPER_MARIO)
            else:
                print("Invalid choice. Returning to main menu.")
        elif choice == "2":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please select 1 or 2.")

if __name__ == "__main__":
    try:
        main()
    finally:
        lgpio.gpiochip_close(chip)  # Close the GPIO chip on exit