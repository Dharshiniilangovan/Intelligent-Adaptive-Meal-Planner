"""Meal planning: confirm preferences, then run live or preview saved results."""
from datetime import date
import re
import streamlit as st

from app.components.ui_state import current_pantry, csv_values, normalized_list
from app.components.planner_bridge import generate
from app.components.demo_loader import load_demo_plan
from app.components.preference_summary import show_preferences
from app.components.presentation import show_meals
from src.input_parser.natural_language_parser import UserInputParser


@st.cache_resource
def get_parser():
    return UserInputParser()


def duration_hint(text):
    match = re.search(r'\b(?:for\s+)?(\d{1,2})\s*days?\b', text, re.I)
    days = int(match.group(1)) if match else None
    return days if days is not None and 1 <= days <= 30 else None


def meal_hints(text):
    return [m for m in ('breakfast', 'lunch', 'dinner')
            if re.search(rf'\b{m}s?\b', text, re.I)]


def comma_text(value):
    return ', '.join(normalized_list(value))


def reset_plan():
    st.session_state['planner_result'] = None
    st.session_state['preview_mode_active'] = False
    for key in ('live_plan_state', 'live_planner', 'planner_user_state'):
        st.session_state.pop(key, None)
    st.session_state['completed_slot_ids'] = set()


st.title('Plan meals that fit your life')
st.caption('Describe your needs and review the details before creating your plan.')
request = st.text_area(
    'What would you like to plan?',
    placeholder='Plan vegetarian lunches and dinners for 3 days under S$100, avoiding peanuts.',
    height=115,
    key='natural_language_request',
)
if st.button('Analyze request', type='primary'):
    if not request.strip():
        st.error('Enter a request first.')
    else:
        try:
            parsed = get_parser().parse(request).to_dict()
        except Exception as exc:
            st.error(f'Could not analyze your request: {exc}')
        else:
            st.session_state['parsed_result'] = parsed
            st.session_state['confirmed_user_state'] = None
            st.session_state['last_request'] = request
            st.session_state['request_revision'] = st.session_state.get('request_revision', 0) + 1
            reset_plan()

parsed = st.session_state.get('parsed_result')
if parsed is not None:
    data = parsed.get('data') or {}
    revision = st.session_state.get('request_revision', 0)
    source_text = st.session_state.get('last_request', '')
    parsed_meals = [m.lower() for m in normalized_list(data.get('preferred_meal_types'))]
    initial_meals = [m for m in ('breakfast', 'lunch', 'dinner')
                     if m in parsed_meals or m in meal_hints(source_text)]
    initial_days = duration_hint(source_text)
    parsed_diet = normalized_list(data.get('dietary_restrictions'))
    parsed_budget = data.get('budget')

    st.divider()
    st.subheader('Review your preferences')
    st.caption('Check the information carefully, especially allergies and missing fields.')
    a, b, c = st.columns(3)
    a.metric('Budget', f'S${float(parsed_budget):.2f}' if parsed_budget is not None else 'Not detected')
    b.metric('Duration', f'{initial_days} days' if initial_days else 'Not detected')
    c.metric('Meals', ', '.join(m.title() for m in initial_meals) or 'Not detected')

    with st.form(f'confirm_{revision}'):
        left, right = st.columns(2)
        with left:
            budget = st.number_input('Budget (SGD) *', min_value=0.01,
                                     value=float(parsed_budget) if parsed_budget is not None and float(parsed_budget) > 0 else None,
                                     placeholder='Enter your budget', key=f'budget_{revision}')
            days = st.number_input('Number of days *', min_value=1, max_value=30,
                                   value=initial_days, placeholder='Enter number of days', key=f'days_{revision}')
        with right:
            start = st.date_input('Start date *', value=date.today(), key=f'start_{revision}')
            meals = st.multiselect('Meal types *', ['breakfast', 'lunch', 'dinner'],
                                   default=initial_meals, key=f'meals_{revision}')

        st.markdown('**Safety and dietary needs**')
        left, right = st.columns(2)
        diet_options = ['Vegetarian', 'Vegan', 'Gluten-Free', 'Dairy-Free', 'Halal', 'Kosher']
        with left:
            diet = st.multiselect('Dietary restrictions', diet_options,
                                  default=[x for x in parsed_diet if x in diet_options], key=f'diet_{revision}')
            other_diet = st.text_input('Other dietary restrictions',
                                       value=', '.join(x for x in parsed_diet if x not in diet_options),
                                       key=f'other_diet_{revision}')
        with right:
            allergy_text = st.text_input('Allergies (comma-separated)',
                                         value=comma_text(data.get('allergies')),
                                         placeholder='e.g. peanut, shellfish', key=f'allergies_{revision}')
            allergy_confirmed = st.checkbox('I have checked my allergies (including none if blank) *',
                                             key=f'allergy_confirm_{revision}')

        with st.expander('More preferences (optional)'):
            left, right = st.columns(2)
            with left:
                cuisines = st.text_input('Preferred cuisines', value=comma_text(data.get('preferred_cuisines')),
                                         key=f'cuisines_{revision}')
                likes = st.text_input('Preferred ingredients', value=comma_text(data.get('preferred_ingredients')),
                                      key=f'likes_{revision}')
                dislikes = st.text_input('Disliked ingredients', value=comma_text(data.get('disliked_ingredients')),
                                         key=f'dislikes_{revision}')
            with right:
                parsed_hours = data.get('cook_time_preference_hrs')
                cook_minutes = st.number_input('Maximum cooking time per meal (minutes)',
                                                min_value=1, max_value=600,
                                                value=round(float(parsed_hours) * 60) if parsed_hours is not None else None,
                                                placeholder='No limit', key=f'cook_{revision}')
                raw_frequency = data.get('cook_frequency')
                frequency = st.number_input('Cooking frequency (times per week)', min_value=0, max_value=21,
                                            value=int(raw_frequency) if str(raw_frequency or '').isdigit() else None,
                                            placeholder='Not specified', key=f'frequency_{revision}')
                flexible = st.checkbox('Budget is flexible', value=bool(data.get('budget_flexible', False)),
                                       key=f'flexible_{revision}')
            st.caption(f"Pantry items saved: {len(st.session_state.get('pantry_items', []))}. Edit them on the Pantry page.")
        submitted = st.form_submit_button('Confirm preferences', type='primary', use_container_width=True)

    if submitted:
        if budget is None or budget <= 0:
            st.error('Enter a budget greater than zero.')
        elif days is None:
            st.error('Enter the number of days.')
        elif not meals:
            st.error('Choose at least one meal type.')
        elif not allergy_confirmed:
            st.error('Please review and confirm your allergy information.')
        else:
            confirmed = dict(data)
            confirmed.update({
                'budget': float(budget),
                'budget_remaining': float(budget),
                'days': int(days),
                'start_date': start.isoformat(),
                'preferred_meal_types': meals,
                'dietary_restrictions': list(dict.fromkeys(diet + csv_values(other_diet))),
                'allergies': csv_values(allergy_text),
                'preferred_cuisines': csv_values(cuisines),
                'preferred_ingredients': csv_values(likes),
                'disliked_ingredients': csv_values(dislikes),
                'cook_time_preference_hrs': cook_minutes / 60 if cook_minutes is not None else None,
                'cook_frequency': frequency,
                'budget_flexible': flexible,
                'budget_cap': float(budget) + 5.0 if flexible else None,
                'ingredient_availability': current_pantry(),
            })
            st.session_state['confirmed_user_state'] = confirmed
            reset_plan()
            st.success('Preferences saved.')

    confirmed = st.session_state.get('confirmed_user_state')
    if confirmed:
        st.markdown('#### Ready to create your meal plan')
        st.write(f"{confirmed['days']} days · {', '.join(m.title() for m in confirmed['preferred_meal_types'])} · S${confirmed['budget']:.2f} budget")
        show_preferences(confirmed)
        preview = st.toggle('Use saved example for fast UI testing', value=True,
                            help='Loads an earlier E2E result. Does not generate a plan for your current preferences.',
                            key='ui_preview_toggle')
        if preview:
            st.info('Preview mode: this is a saved example, not a plan personalized to your current request. Skip-meal replanning is unavailable in preview mode.')
        if st.button('Load example plan' if preview else 'Generate meal plan',
                     type='primary', use_container_width=True):
            if preview:
                try:
                    result = load_demo_plan()
                except (OSError, ValueError) as exc:
                    st.error(f'Unable to load saved example: {exc}')
                else:
                    reset_plan()
                    st.session_state['planner_result'] = result
                    st.session_state['preview_mode_active'] = True
                    st.success('Saved example loaded. Open Dashboard, Groceries or Nutrition.')
            else:
                with st.spinner('Generating meals and calculating groceries. This can take a while...'):
                    try:
                        result, plan_state, planner_state, planner = generate(confirmed)
                    except Exception as exc:
                        st.error(f'Meal generation failed: {exc}')
                    else:
                        reset_plan()
                        st.session_state['planner_result'] = result
                        st.session_state['live_plan_state'] = plan_state
                        st.session_state['planner_user_state'] = planner_state
                        st.session_state['live_planner'] = planner
                        st.success('Your meal plan is ready. Open Dashboard, Groceries or Nutrition.')

        result = st.session_state.get('planner_result')
        if result:
            if st.session_state.get('preview_mode_active'):
                st.caption('Viewing a saved example. Current preferences were not used to generate these meals.')
            meals = (result.get('plan') or {}).get('selected_meals') or []
            if meals:
                show_meals(meals)
            else:
                st.info('No meals to display in this result.')
