"""Week 4 barge-in drill for VoxSell AI.

Run with:
    python barge_in.py
"""

fake_gemini_stream = [
    {"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": "audio-chunk-1"}}]}}},
    {"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": "audio-chunk-2"}}]}}},
    {"serverContent": {"interrupted": True}},
    {"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": "new-response-chunk"}}]}}},
]

playback_queue = []


def handle_gemini_message(message: dict):
    content = message.get("serverContent", {})

    if content.get("interrupted"):
        playback_queue.clear()
        print(">>> INTERRUPTED! Backend queue flushed.")
        print(">>> Send {'type': 'flush'} to the frontend immediately.")
        return

    for part in content.get("modelTurn", {}).get("parts", []):
        inline_data = part.get("inlineData")
        if inline_data:
            playback_queue.append(inline_data["data"])
            print(f"Queued audio chunk. Queue size: {len(playback_queue)}")


for msg in fake_gemini_stream:
    handle_gemini_message(msg)

print(f"Final queue: {playback_queue}")

