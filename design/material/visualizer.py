import cv2
import numpy as np
import librosa
from moviepy import VideoClip, ImageClip, AudioFileClip, CompositeVideoClip
import argparse

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Create a video with an audio visualizer over a background image.")
    parser.add_argument("image", help="Path to the background image file (e.g., JPG, PNG)")
    parser.add_argument("audio", help="Path to the audio file (e.g., MP3, WAV)")
    parser.add_argument("-o", "--output", default="output.mp4", help="Output video file path (default: output.mp4)")
    args = parser.parse_args()

    # Load the audio file
    y, sr = librosa.load(args.audio)
    audio_duration = len(y) / sr

    # Compute the mel spectrogram with 20 mel bands
    melspec = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=20)
    max_val = np.max(melspec)  # For normalizing bar heights
    hop_length = 512  # Default hop length in librosa

    # Load and prepare the background image
    bg_img = cv2.imread(args.image)
    if bg_img is None:
        print(f"Error: Could not load image file '{args.image}'.")
        return
    bg_img = cv2.cvtColor(bg_img, cv2.COLOR_BGR2RGB)  # Convert BGR to RGB for MoviePy
    bg_height, bg_width = bg_img.shape[:2]

    # Define visualizer parameters
    num_bars = 20
    max_bar_height = 1200  # Maximum height of bars in pixels
    margin = 50  # Margin from left and right edges
    space = 10  # Space between bars in pixels
    bar_width = (bg_width - 2 * margin - (num_bars - 1) * space) // num_bars

    # Define the frame generation function for the visualizer
    def make_frame(t):
        # Map video time to spectrogram time index
        i = min(int(round(t * sr / hop_length)), melspec.shape[1] - 1)
        spec_t = melspec[:, i]  # Spectrum at time t

        # Compute bar heights
        bar_heights = (spec_t / max_val) * max_bar_height
        bar_heights = bar_heights.astype(int)

        # Create a blank image with alpha channel (transparent)
        img = np.zeros((bg_height, bg_width, 4), dtype=np.uint8)

        # Draw the visualizer bars
        for j in range(num_bars):
            x_left = margin + j * (bar_width + space)
            x_right = x_left + bar_width
            y_bottom = bg_height  # Bars start from the bottom
            y_top = max(0, bg_height - bar_heights[j])  # Bars grow upward, clamp at top

            # Ensure integer coordinates
            x_left, x_right = int(x_left), int(x_right)
            y_top, y_bottom = int(y_top), int(y_bottom)

            # Draw the bar (white, fully opaque)
            img[y_top:y_bottom, x_left:x_right, :] = [255, 255, 255, 255]

        return img

    # Create the background clip
    background_clip = ImageClip(bg_img, duration=audio_duration)

    # Create the visualizer clip
    visualizer_clip = VideoClip(make_frame, duration=audio_duration)

    # Composite the background and visualizer
    final_clip = CompositeVideoClip([background_clip, visualizer_clip])

    # Add the audio to the video
    audio_clip = AudioFileClip(args.audio)
    final_clip = final_clip.with_audio(audio_clip)

    # Write the final video file
    print(f"Generating video: '{args.output}'")
    final_clip.write_videofile(args.output, fps=30, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    main()