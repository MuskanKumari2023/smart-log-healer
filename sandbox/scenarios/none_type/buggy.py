def get_user_email(user_id: int) -> str:
    user_record = database_fetch_by_id(user_id)  # returns None if missing
    return user_record["email"]


def database_fetch_by_id(user_id: int):
    if user_id == 999:
        return None
    return {"email": f"user{user_id}@example.com"}
