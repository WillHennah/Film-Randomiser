from pathlib import Path
import json
import random
import time
import pandas as pd
import streamlit as st
from datetime import date

FAMILY = ["William", "Henna", "Miilo", "Aimi"]
DATA_FILE = Path("watched_films.csv")
CHOICES_FILE = Path("current_film_choices.json")

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="Family Film Randomiser",
    page_icon="🎬",
    layout="centered",
)

# ---------------------------------------------------------
# Film choice storage
# ---------------------------------------------------------

def load_film_choices():
    """Load the current film nominations from disk."""

    if not CHOICES_FILE.exists():
        return {
            person: []
            for person in FAMILY
        }

    with open(CHOICES_FILE, "r", encoding="utf-8") as file:
        choices = json.load(file)

    # Make sure every current family member exists
    for person in FAMILY:
        choices.setdefault(person, [])

    return choices

def save_film_choices(choices):
    """Save the current film nominations to disk."""

    with open(CHOICES_FILE, "w", encoding="utf-8") as file:
        json.dump(
            choices,
            file,
            indent=4,
            ensure_ascii=False,
        )

def add_watched_film(film_name, chooser):
    """
    Add a confirmed film to the watched-film history.
    """

    watched_date = date.today().strftime("%d.%m.%Y")

    new_row = pd.DataFrame(
        [{
            "Name": film_name,
            "Chooser": chooser,
            "Watched Date": watched_date,
        }]
    )

    new_row.to_csv(
        DATA_FILE,
        mode="a",
        header=False,
        index=False,
    )

def remove_selected_film(chooser, film_name):
    """
    Remove the confirmed watched film from the chooser's
    nominations while leaving all other nominations intact.
    """

    choices = st.session_state.film_choices.get(chooser, [])

    updated_choices = [
        film
        for film in choices
        if film != film_name
    ]

    st.session_state.film_choices[chooser] = updated_choices

    save_film_choices(
        st.session_state.film_choices
    )

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
    st.session_state.film_choices = load_film_choices()

if "draw_result" not in st.session_state:
    st.session_state.draw_result = None

if "reveal_draw" not in st.session_state:
    st.session_state.reveal_draw = False

if "confirmation_message" not in st.session_state:
    st.session_state.confirmation_message = None

# ---------------------------------------------------------
# Load film history
# ---------------------------------------------------------

@st.cache_data
def load_history():
    return pd.read_csv(DATA_FILE)


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

st.subheader("🎟️ This week's films")

st.write(
    "Everyone nominates four films they'd be happy to watch. "
    "**All four films have an equal chance of being selected.**"
)

tabs = st.tabs(FAMILY)

for tab, person in zip(tabs, FAMILY):

    with tab:

        st.markdown(f"### 🎬 {person}'s films")

        existing_choices = st.session_state.film_choices[person]

        with st.form(key=f"{person}_film_form"):

            film_1 = st.text_input(
                "Film 1",
                value=existing_choices[0]
                if len(existing_choices) > 0 else "",
                key=f"{person}_film_1",
            )

            film_2 = st.text_input(
                "Film 2",
                value=existing_choices[1]
                if len(existing_choices) > 1 else "",
                key=f"{person}_film_2",
            )

            film_3 = st.text_input(
                "Film 3",
                value=existing_choices[2]
                if len(existing_choices) > 2 else "",
                key=f"{person}_film_3",
            )

            film_4 = st.text_input(
                "Film 4",
                value=existing_choices[3]
                if len(existing_choices) > 3 else "",
                key=f"{person}_film_4",
            )

            submitted = st.form_submit_button(
                "Save my films",
                use_container_width=True,
            )

        if submitted:

            choices = [
                film_1.strip(),
                film_2.strip(),
                film_3.strip(),
                film_4.strip(),
            ]

            # Check that all four nominations have been entered
            if any(choice == "" for choice in choices):

                st.error(
                    "Please nominate four films before saving."
                )

            # Prevent someone nominating the same film twice
            elif len(set(choice.lower() for choice in choices)) < 4:

                st.error(
                    "You've nominated the same film more than once."
                )

            else:

                st.session_state.film_choices[person] = choices

                save_film_choices(
                    st.session_state.film_choices
                )

                st.success(
                    f"✅ {person}'s four films have been saved."
                )

        # Show submission status
        if len(st.session_state.film_choices[person]) == 4:

            st.caption("✅ Four films submitted")

        else:

            st.caption("⏳ Waiting for four films")

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

            # Calculate result FIRST
            chooser, reason = choose_family_member(
                family_counts=family_counts,
                last_chooser=last_chooser,
            )

            selected_film = choose_film(
                chooser=chooser,
                film_choices=st.session_state.film_choices,
            )

            # Store result
            st.session_state.draw_result = {
                "chooser": chooser,
                "film": selected_film,
                "reason": reason,
            }

            # Mark this as a new result needing a reveal
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

            # Add film to permanent history
            add_watched_film(
                film_name=selected_film,
                chooser=chooser,
            )

            # Remove only the selected film from the
            # chooser's persistent nominations
            remove_selected_film(
                chooser=chooser,
                film_name=selected_film,
            )

            # Clear draw state
            st.session_state.draw_result = None
            st.session_state.reveal_draw = False

            # Force historical data to reload
            st.cache_data.clear()

            st.session_state.confirmation_message = (
                f"🎉 {selected_film} has been added "
                f"to the family film history. "
                f"{chooser} can now add a replacement film."
            )

            st.rerun()

        # -------------------------------------------------
        # Development redraw
        # -------------------------------------------------

        if reset_clicked:

            st.session_state.draw_result = None
            st.session_state.reveal_draw = False

            st.rerun()