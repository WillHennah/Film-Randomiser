
import random
import time
import base64
import hashlib
import hmac
import pandas as pd
import streamlit as st
from datetime import date
from supabase import create_client

FAMILY = ["William", "Henna", "Miilo", "Aimi"]

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="Family Film Randomiser",
    page_icon="🎬",
    layout="centered",
)

# ---------------------------------------------------------
# Supabase
# ---------------------------------------------------------

@st.cache_resource
def get_supabase_client():

    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


supabase = get_supabase_client()

# ---------------------------------------------------------
# Film choice storage
# ---------------------------------------------------------

def hash_pin(pin, salt):
    """
    Derive a PIN hash using the same settings used
    by setup_family_pins.py.
    """

    return hashlib.scrypt(
        pin.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )

def verify_family_pin(person, entered_pin):
    """
    Verify a family member's PIN without exposing or
    storing the original PIN.
    """

    response = (
        supabase
        .table("family_members")
        .select("pin_salt, pin_hash, active")
        .eq("name", person)
        .limit(1)
        .execute()
    )

    if not response.data:
        return False

    record = response.data[0]

    if not record["active"]:
        return False

    salt = base64.b64decode(
        record["pin_salt"]
    )

    expected_hash = base64.b64decode(
        record["pin_hash"]
    )

    entered_hash = hash_pin(
        pin=entered_pin,
        salt=salt,
    )

    return hmac.compare_digest(
        entered_hash,
        expected_hash,
    )

def load_film_choices_from_supabase():

    response = (
        supabase
        .table("film_choices")
        .select("family_member, film_title, created_at")
        .order("created_at")
        .execute()
    )

    choices = {
        person: []
        for person in FAMILY
    }

    for row in response.data:

        person = row["family_member"]
        film = row["film_title"]

        if person in choices:
            choices[person].append(film)

    return choices

def refresh_film_choices():
    """
    Reload the current nominations from Supabase into
    this browser session.
    """

    st.session_state.film_choices = (
        load_film_choices_from_supabase()
    )

def save_person_film_choices(person, choices):
    """
    Save one family member's nominations.

    The caller must be the currently authenticated
    family member.
    """

    if (
        st.session_state.logged_in_user
        != person
    ):

        raise PermissionError(
            "You can only edit your own film choices."
        )

    (
        supabase
        .table("film_choices")
        .delete()
        .eq("family_member", person)
        .execute()
    )

    rows = [
        {
            "family_member": person,
            "film_title": film,
        }
        for film in choices
        if film.strip()
    ]

    if rows:

        (
            supabase
            .table("film_choices")
            .insert(rows)
            .execute()
        )

def add_watched_film(film_name, chooser):
    """
    Add a confirmed watched film directly to Supabase.
    """

    watched_date = date.today().isoformat()

    (
        supabase
        .table("watched_films")
        .insert({
            "film_title": film_name,
            "chooser": chooser,
            "watched_date": watched_date,
        })
        .execute()
    )

def remove_selected_film(chooser, film_name):
    """
    Remove the watched film from Supabase and from
    this session's nominations.
    """

    (
        supabase
        .table("film_choices")
        .delete()
        .eq("family_member", chooser)
        .eq("film_title", film_name)
        .execute()
    )

    updated_choices = [
        film
        for film in st.session_state.film_choices.get(
            chooser, []
        )
        if film != film_name
    ]

    st.session_state.film_choices[chooser] = updated_choices

def load_current_draw():
    """
    Load the shared pending draw from Supabase.

    Returns:
        dict: current draw when one exists
        None: when there is no pending draw
    """

    response = (
        supabase
        .table("current_draw")
        .select(
            "chooser, film_title, reason, drawn_at"
        )
        .eq("singleton_id", 1)
        .limit(1)
        .execute()
    )

    if (
        response is None
        or not response.data
    ):
        return None

    row = response.data[0]

    return {
        "chooser": row["chooser"],
        "film": row["film_title"],
        "reason": row["reason"],
        "drawn_at": row["drawn_at"],
    }

def create_or_get_current_draw(
    chooser,
    film_title,
    reason,
):
    """
    Propose a draw to Supabase.

    If another session has already created a pending draw,
    Supabase returns that existing result instead.
    """

    response = (
        supabase
        .rpc(
            "create_or_get_current_draw",
            {
                "proposed_chooser": chooser,
                "proposed_film_title": film_title,
                "proposed_reason": reason,
            },
        )
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Supabase did not return a draw result."
        )

    row = response.data[0]

    return {
        "chooser": row["chooser"],
        "film": row["film_title"],
        "reason": row["reason"],
        "drawn_at": row["drawn_at"],
    }

def delete_current_draw():
    """
    Delete the shared pending draw.
    Used only by the development reset control.
    """

    (
        supabase
        .table("current_draw")
        .delete()
        .eq("singleton_id", 1)
        .execute()
    )

def confirm_shared_draw():
    """
    Atomically confirm the shared draw in Supabase.
    """

    response = (
        supabase
        .rpc("confirm_current_draw")
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Supabase did not return confirmation details."
        )

    return response.data[0]

# ---------------------------------------------------------
# Film selection logic
# ---------------------------------------------------------

def choose_family_member(family_counts, last_chooser):
    """
    Choose whose film will be selected.

    Rules:
    1. If someone is 5+ selections behind, priority goes to
       the lagging family member.
    2. If multiple people are equally far behind, randomly
       choose between them.
    3. Otherwise, exclude the person who had the previous
       selection and randomly choose between everyone else.
    """

    highest_total = max(family_counts.values())
    lowest_total = min(family_counts.values())

    difference = highest_total - lowest_total

    lagging_members = [
        person
        for person, count in family_counts.items()
        if count == lowest_total
    ]

    # Five-behind rule
    if difference >= 5:

        chooser = random.choice(lagging_members)

        return chooser, "five_behind"

    # Normal selection
    eligible_members = [
        person
        for person in FAMILY
        if person != last_chooser
    ]

    chooser = random.choice(eligible_members)

    return chooser, "standard"

def choose_film(chooser, film_choices):
    """
    Randomly choose one of the selected person's four films.

    All four nominations have equal probability.
    """

    choices = film_choices.get(chooser, [])

    if len(choices) != 4:
        raise ValueError(
            f"{chooser} does not have four submitted films."
        )

    return random.choice(choices)

# ---------------------------------------------------------
# Session state
# ---------------------------------------------------------

if "film_choices" not in st.session_state:
    st.session_state.film_choices = (
        load_film_choices_from_supabase()
    )

if "draw_result" not in st.session_state:
    st.session_state.draw_result = load_current_draw()

if "reveal_draw" not in st.session_state:
    st.session_state.reveal_draw = False

if "confirmation_message" not in st.session_state:
    st.session_state.confirmation_message = None

if "choice_refresh_counter" not in st.session_state:
    st.session_state.choice_refresh_counter = 0

if "save_message" not in st.session_state:
    st.session_state.save_message = None

if "draw_message" not in st.session_state:
    st.session_state.draw_message = None

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

if "login_error" not in st.session_state:
    st.session_state.login_error = None

# ---------------------------------------------------------
# Load film history
# ---------------------------------------------------------
@st.cache_data
def load_history():
    """
    Load the complete watched-film history from Supabase
    and return it in the format expected by the app.
    """

    response = (
        supabase
        .table("watched_films")
        .select("film_title, chooser, watched_date")
        .order("watched_date")
        .execute()
    )

    watched = pd.DataFrame(response.data)

    # Handle an empty database gracefully
    if watched.empty:
        return pd.DataFrame(
            columns=[
                "Name",
                "Chooser",
                "Watched Date",
            ]
        )

    watched = watched.rename(
        columns={
            "film_title": "Name",
            "chooser": "Chooser",
            "watched_date": "Watched Date",
        }
    )

    # Convert YYYY-MM-DD from Supabase back to the
    # DD.MM.YYYY format used throughout the existing app
    watched["Watched Date"] = (
        pd.to_datetime(
            watched["Watched Date"],
            errors="coerce",
        )
        .dt.strftime("%d.%m.%Y")
    )

    return watched

watched = load_history()

# ---------------------------------------------------------
# Prepare history data
# ---------------------------------------------------------

watched["Watched Date Parsed"] = pd.to_datetime(
    watched["Watched Date"],
    format="%d.%m.%Y",
    errors="coerce",
)

# ---------------------------------------------------------
# Header
# ---------------------------------------------------------

st.title("🎬 Family Film Randomiser")

if st.session_state.confirmation_message:

    st.success(
        st.session_state.confirmation_message
    )

    st.session_state.confirmation_message = None

st.write(
    "Everyone chooses four films. "
    "Then we let the randomiser decide what we're watching."
)

# ---------------------------------------------------------
# Family login
# ---------------------------------------------------------

if st.session_state.logged_in_user is None:

    st.subheader("🔐 Who are you?")

    with st.form("family_login_form"):

        selected_person = st.selectbox(
            "Family member",
            FAMILY,
        )

        entered_pin = st.text_input(
            "PIN",
            type="password",
            max_chars=8,
        )

        login_clicked = st.form_submit_button(
            "Log in",
            type="primary",
            use_container_width=True,
        )

    if login_clicked:

        if verify_family_pin(
            person=selected_person,
            entered_pin=entered_pin,
        ):

            st.session_state.logged_in_user = (
                selected_person
            )

            st.session_state.login_error = None

            st.rerun()

        else:

            st.session_state.login_error = (
                "The name and PIN did not match."
            )

    if st.session_state.login_error:

        st.error(
            st.session_state.login_error
        )

    st.stop()

identity_col, logout_col = st.columns(
    [3, 1],
    vertical_alignment="center",
)

with identity_col:

    st.caption(
        f"Signed in as "
        f"**{st.session_state.logged_in_user}**"
    )

with logout_col:

    if st.button(
        "Log out",
        use_container_width=True,
    ):

        st.session_state.logged_in_user = None
        st.session_state.login_error = None

        st.rerun()

st.divider()


# ---------------------------------------------------------
# Last film
# ---------------------------------------------------------

st.subheader("🍿 Last time...")

if not watched.empty:

    last_row = watched.iloc[-1]

    last_chooser = last_row["Chooser"]
    last_film = last_row["Name"]
    last_date = last_row["Watched Date"]

    st.markdown(
        f"""
        **{last_film}**

        Chosen by **{last_chooser}**

        Watched on **{last_date}**
        """
    )

else:

    last_chooser = None

    st.info("No films have been recorded yet.")


st.divider()


# ---------------------------------------------------------
# Current totals
# ---------------------------------------------------------

st.subheader("🏆 Current totals")

chooser_counts = watched["Chooser"].value_counts()

family_counts = {
    person: int(chooser_counts.get(person, 0))
    for person in FAMILY
}

columns = st.columns(4)

for column, person in zip(columns, FAMILY):

    with column:
        st.metric(
            label=person,
            value=family_counts[person],
        )


total_films = (
    watched["Name"]
    .fillna("")
    .astype(str)
    .str.strip()
    .ne("")
    .sum()
)

recent_count = int(
    chooser_counts.get("Recent", 0)
)

other_count = int(
    chooser_counts.get("Other", 0)
)

st.caption(
    f"We have watched **{total_films} films** "
    "as a family."
)

if recent_count or other_count:

    st.caption(
        f"That includes {recent_count} new-release "
        f"selections and {other_count} films watched "
        "for other reasons."
    )

# ---------------------------------------------------------
# Selection balance chart
# ---------------------------------------------------------

balance_df = pd.DataFrame({
    "Family member": FAMILY,
    "Films selected": [
        family_counts[person]
        for person in FAMILY
    ],
})

balance_df = balance_df.set_index("Family member")

st.markdown("#### ⚖️ Selection balance")

st.bar_chart(
    balance_df,
    horizontal=True,
)

highest_count = max(family_counts.values())
lowest_count = min(family_counts.values())

current_gap = highest_count - lowest_count

if current_gap == 0:

    st.success(
        "⚖️ Perfectly balanced! Everyone has had "
        "the same number of selections."
    )

elif current_gap == 1:

    st.success(
        "⚖️ Very balanced. Everyone is within "
        "one selection of each other."
    )

elif current_gap < 5:

    st.info(
        f"⚖️ The current spread is {current_gap} selections."
    )

else:

    st.warning(
        f"⚖️ The current spread is {current_gap} selections. "
        "The catch-up rule is active."
    )

# ---------------------------------------------------------
# Recent films
# ---------------------------------------------------------

st.markdown("#### 🍿 Recently watched")

recent_films = (
    watched
    .sort_values(
        "Watched Date Parsed",
        ascending=False,
    )
    .head(10)
    [["Name", "Chooser", "Watched Date"]]
)

recent_films = recent_films.rename(
    columns={
        "Name": "Film",
        "Chooser": "Choice",
        "Watched Date": "Watched",
    }
)

st.dataframe(
    recent_films,
    hide_index=True,
    width='stretch',
)

with st.expander("🎞️ View full film history"):

    full_history = (
        watched
        .sort_values(
            "Watched Date Parsed",
            ascending=False,
        )
        [["Name", "Chooser", "Watched Date"]]
        .rename(
            columns={
                "Name": "Film",
                "Chooser": "Choice",
                "Watched Date": "Watched",
            }
        )
    )

    st.dataframe(
        full_history,
        hide_index=True,
        width='stretch',
    )

# ---------------------------------------------------------
# Films over time
# ---------------------------------------------------------

st.markdown("#### 📅 Family film history")

valid_dates = watched.dropna(
    subset=["Watched Date Parsed"]
).copy()

valid_dates["Year"] = (
    valid_dates["Watched Date Parsed"].dt.year
)

films_per_year = (
    valid_dates
    .groupby("Year")
    .size()
    .reset_index(name="Films watched")
)

films_per_year["Year"] = (
    films_per_year["Year"].astype(str)
)

films_per_year = films_per_year.set_index("Year")

st.bar_chart(
    films_per_year
)

st.divider()


# ---------------------------------------------------------
# Fairness check
# ---------------------------------------------------------

st.subheader("⚖️ This week's draw")

highest_total = max(family_counts.values())
lowest_total = min(family_counts.values())

difference = highest_total - lowest_total

lagging_members = [
    person
    for person, count in family_counts.items()
    if count == lowest_total
]


if difference >= 5:

    if len(lagging_members) == 1:

        st.warning(
            f"⭐ {lagging_members[0]} is five or more films "
            "behind and gets priority this week."
        )

    else:

        names = ", ".join(lagging_members)

        st.warning(
            f"⭐ {names} are tied at five or more films "
            "behind. The randomiser will choose between them."
        )

else:

    st.success(
        "Everyone is within five films. "
        "The normal randomiser will be used."
    )

    if last_chooser in FAMILY:

        st.info(
            f"{last_chooser} had the last selection, "
            "so they aren't eligible this week."
        )


# ---------------------------------------------------------
# Film nominations
# ---------------------------------------------------------

st.divider()

st.subheader("🎟️ Your film choices")

person = st.session_state.logged_in_user

st.write(
    f"Hi **{person}**! Keep four films here that you'd "
    "be happy for the family to watch. "
    "**All four films have an equal chance of being selected.**"
)

# ---------------------------------------------------------
# Refresh nominations from Supabase
# ---------------------------------------------------------

if st.button(
    "🔄 Refresh film choices",
    use_container_width=True,
):

    refresh_film_choices()

    st.session_state.choice_refresh_counter += 1

    st.rerun()


# ---------------------------------------------------------
# Current logged-in user's films
# ---------------------------------------------------------

existing_choices = (
    st.session_state.film_choices.get(
        person,
        [],
    )
)

st.markdown(f"### 🎬 {person}'s films")

with st.form(
    key=f"{person}_film_form"
):

    film_1 = st.text_input(
        "Film 1",
        value=(
            existing_choices[0]
            if len(existing_choices) > 0
            else ""
        ),
        key=(
            f"{person}_film_1_"
            f"{st.session_state.choice_refresh_counter}"
        ),
    )

    film_2 = st.text_input(
        "Film 2",
        value=(
            existing_choices[1]
            if len(existing_choices) > 1
            else ""
        ),
        key=(
            f"{person}_film_2_"
            f"{st.session_state.choice_refresh_counter}"
        ),
    )

    film_3 = st.text_input(
        "Film 3",
        value=(
            existing_choices[2]
            if len(existing_choices) > 2
            else ""
        ),
        key=(
            f"{person}_film_3_"
            f"{st.session_state.choice_refresh_counter}"
        ),
    )

    film_4 = st.text_input(
        "Film 4",
        value=(
            existing_choices[3]
            if len(existing_choices) > 3
            else ""
        ),
        key=(
            f"{person}_film_4_"
            f"{st.session_state.choice_refresh_counter}"
        ),
    )

    submitted = st.form_submit_button(
        "Save my films",
        type="primary",
        use_container_width=True,
    )


# ---------------------------------------------------------
# Save nominations
# ---------------------------------------------------------

if submitted:

    choices = [
        film_1.strip(),
        film_2.strip(),
        film_3.strip(),
        film_4.strip(),
    ]

    if any(
        choice == ""
        for choice in choices
    ):

        st.error(
            "Please nominate four films before saving."
        )

    elif len(
        set(
            choice.lower()
            for choice in choices
        )
    ) < 4:

        st.error(
            "You've nominated the same film more than once."
        )

    else:

        try:

            save_person_film_choices(
                person=person,
                choices=choices,
            )

            refresh_film_choices()

            st.session_state.choice_refresh_counter += 1

            st.session_state.save_message = (
                "✅ Your four films have been saved."
            )

            st.rerun()

        except Exception as error:

            st.error(
                f"Could not save your films: {error}"
            )


# ---------------------------------------------------------
# Submission status
# ---------------------------------------------------------

if len(
    st.session_state.film_choices.get(
        person,
        [],
    )
) == 4:

    st.caption(
        "✅ You have four films ready for the next draw."
    )

else:

    missing_count = (
        4
        - len(
            st.session_state.film_choices.get(
                person,
                [],
            )
        )
    )

    st.warning(
        f"⏳ You need to add {missing_count} more "
        "film"
        f"{'s' if missing_count != 1 else ''} "
        "before the next draw."
    )

# ---------------------------------------------------------
# Submission progress
# ---------------------------------------------------------

st.divider()

submitted_people = [
    person
    for person in FAMILY
    if len(st.session_state.film_choices[person]) == 4
]

number_submitted = len(submitted_people)

st.subheader("🎬 Ready for movie night?")

st.progress(number_submitted / len(FAMILY))

st.write(
    f"**{number_submitted} of {len(FAMILY)}** "
    "family members have submitted their films."
)

if number_submitted == len(FAMILY):

    st.success(
        "🍿 Everyone has submitted four films. "
        "The draw is ready!"
    )

else:

    waiting_for = [
        person
        for person in FAMILY
        if person not in submitted_people
    ]

    st.caption(
        "Still waiting for: "
        + ", ".join(waiting_for)
    )

# ---------------------------------------------------------
# Draw
# ---------------------------------------------------------

st.divider()
st.subheader("🎲 The draw")

if st.button(
    "🔄 Refresh draw status",
    use_container_width=True,
):

    previous_draw = st.session_state.draw_result
    latest_draw = load_current_draw()

    st.session_state.draw_result = latest_draw

    # Animate only when this browser discovers a new draw
    if previous_draw is None and latest_draw is not None:
        st.session_state.reveal_draw = True
    else:
        st.session_state.reveal_draw = False

    st.rerun()

if st.session_state.draw_message:

    st.warning(
        st.session_state.draw_message
    )

    st.session_state.draw_message = None

all_submitted = all(
    len(st.session_state.film_choices.get(person, [])) == 4
    for person in FAMILY
)

# ---------------------------------------------------------
# Not everyone has four films
# ---------------------------------------------------------

if not all_submitted:

    st.info(
        "The draw will become available once everyone "
        "has submitted four films."
    )

# ---------------------------------------------------------
# Everyone is ready
# ---------------------------------------------------------

else:

    # -----------------------------------------------------
    # No result yet -> show Draw button
    # -----------------------------------------------------

    if st.session_state.draw_result is None:

        st.write(
            "Everyone's films are in. "
            "It's time to choose this week's film."
        )

        draw_clicked = st.button(
            "🎬 DRAW THE FILM",
            type="primary",
            use_container_width=True,
        )

        if draw_clicked:

            latest_choices = (
                load_film_choices_from_supabase()
            )

            latest_all_submitted = all(
                len(latest_choices.get(person, [])) == 4
                for person in FAMILY
            )

            if not latest_all_submitted:

                st.session_state.film_choices = latest_choices

                st.session_state.choice_refresh_counter += 1

                st.session_state.draw_message = (
                    "The nominations changed in another session. "
                    "Everyone must have four films before drawing."
                )

                st.rerun()

            chooser, reason = choose_family_member(
                family_counts=family_counts,
                last_chooser=last_chooser,
            )

            selected_film = choose_film(
                chooser=chooser,
                film_choices=latest_choices,
            )

            st.session_state.film_choices = latest_choices

            shared_result = create_or_get_current_draw(
                chooser=chooser,
                film_title=selected_film,
                reason=reason,
            )

            st.session_state.draw_result = shared_result
            st.session_state.reveal_draw = True

            st.rerun()

    # -----------------------------------------------------
    # Result exists -> reveal/display it
    # -----------------------------------------------------

    else:

        result = st.session_state.draw_result

        chooser = result["chooser"]
        selected_film = result["film"]
        reason = result["reason"]

        # -------------------------------------------------
        # Animated reveal - only once
        # -------------------------------------------------

        if st.session_state.reveal_draw:

            reveal_box = st.empty()

            reveal_box.markdown(
                "### 🎲 Choosing whose film it will be..."
            )

            time.sleep(1.5)

            reveal_box.markdown(
                f"## 🎉 {chooser}!"
            )

            time.sleep(1.5)

            reveal_box.markdown(
                f"### 🎬 Choosing one of {chooser}'s four films..."
            )

            time.sleep(1.8)

            reveal_box.markdown(
                f"# 🍿 {selected_film}"
            )

            st.balloons()

            time.sleep(1)

            # Reveal has now been completed
            st.session_state.reveal_draw = False

        # -------------------------------------------------
        # Permanent result display
        # -------------------------------------------------

        st.success(
            "🎉 This week's family film has been chosen!"
        )

        st.markdown(
            f"""
            ## 🎬 {selected_film}

            ### {chooser}'s choice
            """
        )

        if reason == "five_behind":

            st.caption(
                f"{chooser} received this week's selection "
                "through the five-behind rule."
            )

        else:

            st.caption(
                "Selected through the normal random draw."
            )

        # -------------------------------------------------
        # Result actions
        # -------------------------------------------------

        st.divider()

        confirm_col, reset_col = st.columns(2)

        with confirm_col:

            confirm_clicked = st.button(
                "✅ Confirm as watched",
                type="primary",
                use_container_width=True,
            )

        with reset_col:

            reset_clicked = st.button(
                "🔄 Reset test draw",
                use_container_width=True,
            )

        # -------------------------------------------------
        # Confirm film
        # -------------------------------------------------

        if confirm_clicked:

            try:

                confirmed = confirm_shared_draw()

                confirmed_film = confirmed["confirmed_film_title"]
                confirmed_chooser = confirmed["confirmed_chooser"]

                # Reload shared nominations after Supabase
                # removed the watched film
                refresh_film_choices()

                st.session_state.choice_refresh_counter += 1

                # Clear this browser's copy of the shared draw
                st.session_state.draw_result = None
                st.session_state.reveal_draw = False

                # Reload film history on the next run
                st.cache_data.clear()

                st.session_state.confirmation_message = (
                    f"🎉 {confirmed_film} has been added "
                    f"to the family film history. "
                    f"{confirmed_chooser} can now add "
                    "a replacement film."
                )

                st.rerun()

            except Exception as error:

                # Another phone may already have confirmed it.
                latest_draw = load_current_draw()

                st.session_state.draw_result = latest_draw
                st.session_state.reveal_draw = False

                if latest_draw is None:

                    st.session_state.draw_message = (
                        "This draw has already been confirmed "
                        "from another session."
                    )

                    st.cache_data.clear()
                    refresh_film_choices()
                    st.session_state.choice_refresh_counter += 1

                    st.rerun()

                st.error(
                    f"Could not confirm the draw: {error}"
                )

        # -------------------------------------------------
        # Development redraw
        # -------------------------------------------------

        if reset_clicked:

            delete_current_draw()

            st.session_state.draw_result = None
            st.session_state.reveal_draw = False

            st.rerun()