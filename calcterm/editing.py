"""Text-buffer operations shared by the console editors."""


def insert_text_at_cursor(text, cursor, inserted, overwrite=False):
    end = cursor + len(inserted) if overwrite else cursor
    return text[:cursor] + inserted + text[end:], cursor + len(inserted)


def edit_text(text, cursor, key, overwrite=False):
    if key == "LEFT":
        return text, max(0, cursor - 1)
    if key == "RIGHT":
        return text, min(len(text), cursor + 1)
    if key == "HOME":
        return text, 0
    if key == "END":
        return text, len(text)
    if key == "CTRL_U":
        return "", 0
    if key == "BACKSPACE" and cursor:
        return text[:cursor - 1] + text[cursor:], cursor - 1
    if key == "DELETE":
        return text[:cursor] + text[cursor + 1:], cursor
    if len(key) == 1 and key.isprintable():
        return insert_text_at_cursor(text, cursor, key, overwrite)
    return text, cursor
