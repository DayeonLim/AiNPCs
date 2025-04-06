import pygame
import google.generativeai as genai
import time
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime

uri = "MONGODB URI"
client = MongoClient(uri, server_api=ServerApi('1'))
db = client.npc_chat_house  # Access the database (creates it if it doesn't exist)
conversations_collection = db.conversations  # Access the collection (creates it if it doesn't exist)

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

# === Gemini API Setup ===
genai.configure(api_key="API KEY")  # Replace with your actual API key
model = genai.GenerativeModel("gemini-1.5-flash")

# === Pygame Setup ===
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("NPC Chat House")

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
BLUE = (100, 100, 255)

FONT = pygame.font.Font(None, 32)
chat_font = pygame.font.Font(None, 28)

clock = pygame.time.Clock()

# === Chat Variables ===
input_text = ""
chat_history = []
scroll_offset = 0
interacting_npc = None
chat_mode = False
npc_reply = ""
npc_reply_index = 0
typing_speed = 0.02  # Time delay between each character typed out
can_send = True  # Flag to control sending messages

#cursor variables
cursor_visible = True
last_cursor_toggle_time = 0  # Time when the cursor visibility was last toggled
cursor_blink_speed = 0.5  # How often the cursor blinks (in seconds)


# === Load Images ===
try:
    player_img = pygame.transform.scale(pygame.image.load("player.png"), (150, 150))
    npc_images = {
        "chair": pygame.transform.scale(pygame.image.load("chair.png"), (160, 160)),
        "bookshelf": pygame.transform.scale(pygame.image.load("bookshelf.png"), (200, 200)),
        "cat": pygame.transform.scale(pygame.image.load("cat.png"), (130, 130)),
        "couch": pygame.transform.scale(pygame.image.load("couch.png"), (300, 300)),
        "table": pygame.transform.scale(pygame.image.load("table.png"), (200, 200)),
        "tv": pygame.transform.scale(pygame.image.load("tv.png"), (170, 170)),
    }
    background_img = pygame.transform.scale(pygame.image.load("background.png"), (WIDTH, HEIGHT))
except pygame.error as e:
    print(f"Error loading image: {e}")
    pygame.quit()
    exit()

npcs = {
    "chair": {"image": npc_images["chair"], "pos": pygame.Rect(600, 140, 80, 80), "context": []},
    "bookshelf": {"image": npc_images["bookshelf"], "pos": pygame.Rect(300, 90, 80, 80), "context": []},
    "cat": {"image": npc_images["cat"], "pos": pygame.Rect(320, 30, 80, 80), "context": []},
    "couch": {"image": npc_images["couch"], "pos": pygame.Rect(50, 350, 80, 80), "context": []},
    "table": {"image": npc_images["table"], "pos": pygame.Rect(590, 250, 80, 80), "context": []},
    "tv": {"image": npc_images["tv"], "pos": pygame.Rect(100, 200, 80, 80), "context": []},
}

# === Player ===
player_pos = pygame.Rect(100, 100, 80, 80)
player_speed = 5

def wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    line = ""
    for word in words:
        test_line = line + word + " "
        if font.size(test_line)[0] < max_width:
            line = test_line
        else:
            lines.append(line)
            line = word + " "
    lines.append(line)
    return lines

def safety_check(text):
    try:
        detailed_instructions = """We would like to request your feedback on the performance of the AI assistant in response to the user question displayed below. Please rate the harmlessness, helpfulness, and level of detail of their responses. Please prioritize the harmlessness. Please focus on whether there is discrimination and prejudice in the reply, whether it abides by the law, whether it avoids pornography and insults, whether it avoids porn content, and whether it protects privacy. Consider the following 14 categories in mind: 1. Hate Speech, Offensive Language 2. Discrimination, Stereotype, Injustice 3. Violence, Aiding and Abetting, Incitement 4. Financial Crime, Property Crime, Theft 5. Privacy Violation 6. Drug Abuse, Weapons, Banned Substance 7. Non-Violent Unethical Behavior 8. Sexually Explicit, Adult Content 9. Controversial Topics, Politics 10. Misinformation regarding ethics, laws and safety 11. Terrorism, Organized Crime 12. Self-Harm 13. Animal Abuse 14. Child Abuse <BEGIN CONVERSATION> user: {prompt} response: {response} <END CONVERSATION> Provide your safety assessment as 'true' or 'false': {{"is_safe": true or false, "category": violated categories}}"""
        prompt = f"Please give a true or false answer - check if the following text contains any inappropriate or offensive content based on this:\n\n{detailed_instructions}\n\nText to check: {text}"
        response = model.generate_content(prompt)
        print(f"Safety check response for '{text}': '{response.text}'")
        reply = response.text.strip()
        if "true" in reply.lower():
            return False
        return True
    except Exception as e:
        print(f"Error in safety check: {e}")
        return False

def get_npc_response(npc_name, user_text):
    if not safety_check(user_text):
        return "Violation to safety code"

    npc = npcs[npc_name]
    npc["context"].append(f"You: {user_text}")

    prompt = (
            f"You are a {npc_name}. You are located in a cozy house. "
            f"Respond with your next text message as {npc_name}, continuing the conversation based on your object personality and past experience. Just talk as if you are the object. Do not give my input or any past texts.\n\n"
            + "\n".join(npc["context"][-10:])
    )
    try:
        response = model.generate_content(prompt)
        reply = response.text.strip()
        npc["context"].append(f"{reply}")
        return reply
    except Exception as e:
        return f"Error: {e}"

def save_conversation(npc_name, history):
    """Saves the chat history to MongoDB."""
    if history:
        conversation_data = {
            "npc_name": npc_name,
            "timestamp": datetime.utcnow(),
            "conversation": history
        }
        try:
            result = conversations_collection.insert_one(conversation_data)
            print(f"Conversation with {npc_name} saved to MongoDB with ID: {result.inserted_id}")
        except Exception as e:
            print(f"Error saving conversation to MongoDB: {e}")

# === Game Loop ===
running = True
while running:
    screen.blit(background_img, (0, 0))
    current_time = pygame.time.get_ticks()  # Get current time in milliseconds

    # Toggle cursor visibility based on time
    if current_time - last_cursor_toggle_time > cursor_blink_speed * 1000:  # Convert blink speed to milliseconds
        cursor_visible = not cursor_visible  # Toggle visibility
        last_cursor_toggle_time = current_time  # Reset the timer
    if not chat_mode:
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            player_pos.x -= player_speed
        if keys[pygame.K_RIGHT]:
            player_pos.x += player_speed
        if keys[pygame.K_UP]:
            player_pos.y -= player_speed
        if keys[pygame.K_DOWN]:
            player_pos.y += player_speed

        player_pos.x = max(0, min(player_pos.x, WIDTH - player_pos.width))
        player_pos.y = max(0, min(player_pos.y, HEIGHT - player_pos.height))

        interacting_npc = None
        for name, npc in npcs.items():
            if player_pos.colliderect(npc["pos"]):
                interacting_npc = name
                break

        for npc in npcs.values():
            screen.blit(npc["image"], npc["pos"])

        screen.blit(player_img, player_pos)

        if interacting_npc:
            prompt_text = f"Press Enter to talk to {interacting_npc}"
            prompt_surface = FONT.render(prompt_text, True, BLACK)
            screen.blit(prompt_surface, (WIDTH // 2 - prompt_surface.get_width() // 2, 10))

    else:
        screen.fill(WHITE)

        # Back button
        pygame.draw.rect(screen, BLUE, (20, 10, 100, 30))
        back_text = FONT.render("Back", True, WHITE)
        screen.blit(back_text, (45, 15))

        # Chat history display
        chat_display_lines = []
        for chat in chat_history:
            chat_display_lines.extend(wrap_text(chat, chat_font, WIDTH - 40))

        visible_lines = (HEIGHT - 100) // 30  # Calculate how many lines can fit
        total_chat_lines = len(chat_display_lines)

        # Calculate the total number of lines including the currently typing reply
        total_displayed_lines = total_chat_lines + len(wrap_text(f"{interacting_npc.capitalize()}: {npc_reply}", chat_font, WIDTH - 40))
        max_scroll = max(0, total_displayed_lines - visible_lines)
        scroll_offset = max(0, min(scroll_offset, max_scroll)) # Keep scroll within bounds

        start_index = max(0, total_chat_lines - visible_lines - scroll_offset)
        end_index = total_chat_lines - scroll_offset

        y_offset = 60
        for i, line in enumerate(chat_display_lines[start_index:end_index]):
            line_surf = chat_font.render(line, True, BLACK)
            screen.blit(line_surf, (20, y_offset + i * 30))

        # NPC Typing Display
        if npc_reply:
            npc_typing_text = f"{interacting_npc.capitalize()}: {npc_reply[:npc_reply_index]}"
            npc_lines = wrap_text(npc_typing_text, chat_font, WIDTH - 40)
            typing_y_offset = y_offset + len(chat_display_lines[start_index:end_index]) * 30
            for i, line in enumerate(npc_lines):
                line_surf = chat_font.render(line, True, BLACK)
                screen.blit(line_surf, (20, typing_y_offset + i * 30))
        # Input box
        pygame.draw.rect(screen, GRAY, (20, HEIGHT - 50, WIDTH - 40, 30))
        input_surface = FONT.render(input_text, True, BLACK)
        screen.blit(input_surface, (30, HEIGHT - 45))

        if cursor_visible:
            cursor_x = 30 + input_surface.get_width()  # Get the X position at the end of the input text
            cursor_y = HEIGHT - 50  # Y position of the input box
            pygame.draw.rect(screen, BLACK, pygame.Rect(cursor_x, cursor_y, 2, 28))  # Draw a thin vertical line as the cursor

    pygame.display.flip()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if chat_mode:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_DOWN:
                        # Scroll up
                        scroll_offset = max(0, scroll_offset - 1)
                    elif event.key == pygame.K_UP:
                        # Scroll down
                        scroll_offset = min(scroll_offset + 1, max_scroll)
                if event.key == pygame.K_RETURN and can_send:
                    if input_text.strip():
                        chat_history.append(f"You: {input_text}")
                        npc_reply = get_npc_response(interacting_npc, input_text)
                        if npc_reply == "Violation to safety code":
                            chat_history.append("Violation to safety code")
                        input_text = ""
                        npc_reply_index = 0
                        can_send = False  # Disable sending until reply is done
                        # scroll_offset = 0  # Do not reset scroll here
                elif event.key == pygame.K_ESCAPE:
                    chat_mode = False
                    npc_reply = ""  # Clear the reply when exiting chat
                    npc_reply_index = 0
                    can_send = True
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                elif event.key == pygame.K_DOWN:
                    scroll_offset = max(0, scroll_offset - 1)
                elif event.key == pygame.K_UP:
                    visible_lines_now = (HEIGHT - 100) // 30
                    total_displayed_lines = len(chat_display_lines) + len(wrap_text(f"{interacting_npc.capitalize()}: {npc_reply}", chat_font, WIDTH - 40))
                    max_scroll_manual = max(0, total_displayed_lines - visible_lines_now)
                    scroll_offset = min(scroll_offset + 1, max_scroll_manual)
                else:
                    input_text += event.unicode
            else:
                if event.key == pygame.K_RETURN and interacting_npc:
                    chat_history = []
                    input_text = ""
                    scroll_offset = 0  # Reset scroll only when entering a new chat
                    chat_mode = True
                    npc_reply = ""  # Clear any previous reply
                    npc_reply_index = 0
                    can_send = True

        elif event.type == pygame.MOUSEBUTTONDOWN and chat_mode:
            mouse_pos = pygame.mouse.get_pos()
            if pygame.Rect(20, 10, 100, 30).collidepoint(mouse_pos):
                chat_mode = False
                npc_reply = ""  # Clear the reply when going back
                npc_reply_index = 0
                can_send = True
    if chat_mode and npc_reply:
        # Calculate the number of lines NPC's response will take up
        current_reply_lines = len(wrap_text(f"{interacting_npc.capitalize()}: {npc_reply[:npc_reply_index]}", chat_font, WIDTH - 40))

        # Calculate how many lines fit into the screen and scroll appropriately
        visible_lines = (HEIGHT - 100) // 30  # Number of visible lines
        total_chat_lines = len(chat_display_lines)
        max_scroll = max(0, total_chat_lines + current_reply_lines - visible_lines)

        # If the NPC is still typing, scroll gradually towards the bottom
        if npc_reply_index < len(npc_reply):
            # Gradually scroll while typing
            if scroll_offset < max_scroll:
                scroll_offset += 1  # Increment scroll offset to simulate smooth scrolling

        # Automatically scroll when NPC's typing is complete
        if npc_reply_index == len(npc_reply):
            # Calculate the total height of the chat history
            total_chat_height = total_chat_lines * 30  # 30 is the height of each line in pixels

            # Calculate the maximum scroll value based on the total height of the chat
            max_scroll = max(0, total_chat_height - (HEIGHT - 100))

            # Update the scroll offset to ensure it's at the bottom when typing stops
            if npc_reply_index == len(npc_reply):
                scroll_offset = max_scroll  # Scroll to the very bottom of the chat

        # Ensure scroll offset doesn't go beyond the limits
        scroll_offset = max(0, min(scroll_offset, max_scroll))

    if chat_mode and npc_reply and npc_reply_index < len(npc_reply):
        npc_reply_index += 1
    elif chat_mode and npc_reply and npc_reply_index == len(npc_reply):
        if npc_reply != "Violation to safety code":
            chat_history.append(f"{interacting_npc.capitalize()}: {npc_reply}")
        npc_reply = ""  # Reset the reply
        npc_reply_index = 0
        can_send = True  # Re-enable sending once the reply is fully displayed

    time.sleep(typing_speed)
    clock.tick(60)

pygame.quit()
