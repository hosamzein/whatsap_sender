# Requirements Python 3.XX(run once)
# run once the follwoinf coomand from your local shell 
# pip install nicegui pandas openpyxl pywhatkit
# the run the following all in one python script

from nicegui import ui
import pandas as pd
import threading
import time
from io import BytesIO
import pywhatkit
import re

# ---------------- State ----------------
results = []
sending = False
paused = False

uploaded_excel_content = None
uploaded_contacts_df: pd.DataFrame | None = None
filtered_df: pd.DataFrame | None = None

current_idx = -1

progress = None
wait_time_input = None
delay_input = None
uploader = None
processed_count_label = None
percent_label = None
table = None
country_code = None

# Search
search_field_select = None
search_input = None

# Message source / settings
message_source_select = None
custom_message_box = None
variables_container = None  # container for variable chips

# ---------------- Helpers ----------------
def normalize_phone(phone, country_code='+20'):
    phone = str(phone or '').strip().replace(' ', '').replace('-', '')
    if not phone.startswith('+'):
        phone = country_code + phone.lstrip('0')
    return phone

def apply_filter():
    global filtered_df
    if uploaded_contacts_df is None:
        filtered_df = None
        refresh_table()
        return
    field = search_field_select.value if search_field_select else None
    query = (search_input.value or '').strip().lower() if search_input else ''
    if not field or not query:
        filtered_df = uploaded_contacts_df.copy()
    else:
        if field == 'Seq':
            df = uploaded_contacts_df.copy()
            df['_seq_str'] = (df.index + 1).astype(str)
            filtered_df = df[df['_seq_str'].str.contains(query, na=False)].copy()
            filtered_df.drop(columns=['_seq_str'], inplace=True, errors='ignore')
        elif field in uploaded_contacts_df.columns:
            filtered_df = uploaded_contacts_df[
                uploaded_contacts_df[field].astype(str).str.lower().str.contains(query, na=False)
            ].copy()
        else:
            filtered_df = uploaded_contacts_df.copy()
    refresh_table()

def clear_filter():
    if search_input:
        search_input.value = ''
        search_input.update()
    apply_filter()

def render_custom_message(template_text: str, row: pd.Series) -> str:
    pattern = r'{{\s*([^}]+)\s*}}'
    def repl(m):
        col = (m.group(1) or '').strip()
        return str(row.get(col, ''))
    return re.sub(pattern, repl, template_text or '')

def render_custom_message_with_normalized_phone(template_text: str, row: pd.Series, country_code_val: str, phone_column: str) -> str:
    row_for_render = row.copy()
    try:
        raw_phone = row.get(phone_column, '')
        norm_phone = normalize_phone(raw_phone, country_code_val)
    except Exception:
        norm_phone = ''
    row_for_render['Phone'] = norm_phone
    row_for_render['phone'] = norm_phone
    return render_custom_message(template_text, row_for_render)

def refresh_table():
    global table, current_idx
    df_to_show = filtered_df if filtered_df is not None else uploaded_contacts_df
    if df_to_show is not None and table is not None:
        phone_col = next((c for c in df_to_show.columns if c.lower().strip() in {"phone", "phonenumber", "number"}), None)

        columns = [{'name': 'Seq', 'label': 'Seq', 'field': 'Seq'}]
        for col in df_to_show.columns:
            columns.append({'name': col, 'label': col, 'field': col})
        if phone_col:
            columns.append({'name': 'Phone (Normalized)', 'label': 'Phone (Normalized)', 'field': 'Phone (Normalized)'})
        table.columns = columns

        display_rows = []
        for orig_idx, row in df_to_show.iterrows():
            new_row = {'Seq': orig_idx + 1}
            for c in df_to_show.columns:
                new_row[c] = row[c]
            if phone_col:
                try:
                    new_row['Phone (Normalized)'] = normalize_phone(row[phone_col], country_code.value if country_code else '+20')
                except Exception:
                    new_row['Phone (Normalized)'] = ''
            display_rows.append(new_row)
        table.rows = display_rows

        def row_bg(r):
            if current_idx != -1 and r.get('Seq') == current_idx + 1:
                return 'bg-yellow-3'
            return None

        table.row_background = row_bg
        table.update()
    elif table is not None:
        table.rows = []
        table.update()

def poll_results():
    while True:
        refresh_table()
        time.sleep(1)

def insert_placeholder_at_caret_exact(placeholder: str):
    try:
        element_id = custom_message_box._props.get('id') or custom_message_box.id
        if not element_id:
            raise RuntimeError('no element id')
        js = f"""
        (function() {{
            const el = document.getElementById('{element_id}');
            if (!el) return null;
            const start = el.selectionStart ?? 0;
            const end = el.selectionEnd ?? 0;
            const before = el.value.substring(0, start);
            const after = el.value.substring(end);
            const inserted = {placeholder!r};
            const newVal = before + inserted + after;
            const newPos = (before + inserted).length;
            el.value = newVal;
            el.focus();
            el.setSelectionRange(newPos, newPos);
            return newVal;
        }})()
        """
        result = ui.run_javascript(js)
        if isinstance(result, str):
            custom_message_box.value = result
            custom_message_box.update()
        else:
            custom_message_box.value = (custom_message_box.value or '') + placeholder
            custom_message_box.update()
    except Exception:
        custom_message_box.value = (custom_message_box.value or '') + placeholder
        custom_message_box.update()

# ---------------- Sending ----------------
def send_all_pywhatkit(country_code_val: str, excel_bytes, wait_time_seconds, delay_seconds):
    global results, sending, uploaded_contacts_df, paused, current_idx, filtered_df
    results.clear()
    sending = True
    processed = 0
    try:
        df = pd.read_excel(BytesIO(excel_bytes))
        uploaded_contacts_df = df
        filtered_df = uploaded_contacts_df.copy()
        update_search_fields_options()
        apply_filter()
    except Exception as e:
        ui.notify(f"Failed to read Excel: {e}", type="negative")
        sending = False
        if progress is not None:
            progress.value = 0
        if percent_label is not None:
            percent_label.text = '0%'
        if processed_count_label is not None:
            processed_count_label.text = "Processed: 0"
        current_idx = -1
        refresh_table()
        return

    total = len(df)
    if total == 0:
        ui.notify("Excel is empty!", type="warning")
        sending = False
        if progress is not None:
            progress.value = 0
        if percent_label is not None:
            percent_label.text = '0%'
        if processed_count_label is not None:
            processed_count_label.text = "Processed: 0"
        current_idx = -1
        refresh_table()
        return

    phone_column = next((c for c in df.columns if c.lower().strip() in {"phone", "phonenumber", "number"}), None)
    if phone_column is None:
        ui.notify('No column named Phone/Number found!', type='negative')
        sending = False
        current_idx = -1
        refresh_table()
        return
    message_column = next((c for c in df.columns if c.lower().strip() == "message"), None)

    for idx, row in df.iterrows():
        if not sending:
            current_idx = -1
            refresh_table()
            break

        current_idx = idx
        refresh_table()
        if table:
            table.update()

        phone_number = normalize_phone(row[phone_column], country_code_val)

        if message_source_select.value == 'Custom Text':
            msg = render_custom_message_with_normalized_phone(
                str(custom_message_box.value or ''), row, country_code_val, phone_column
            )
        else:
            msg = str(row.get(message_column, '')) if message_column else ''

        try:
            pywhatkit.sendwhatmsg_instantly(
                phone_no=phone_number,
                message=msg,
                wait_time=wait_time_seconds,
                tab_close=True
            )
        except Exception:
            pass

        processed += 1
        if progress is not None:
            progress.value = processed / total
        if processed_count_label is not None:
            processed_count_label.text = f"Processed: {processed} / {total}"
        if percent_label is not None:
            percent_label.text = f'{int((progress.value or 0) * 100)}%'
        if table:
            table.update()

        time.sleep(delay_seconds)

        while paused and sending:
            time.sleep(0.2)

    refresh_table()
    if table:
        table.update()

    sending = False
    current_idx = -1
    if progress is not None:
        progress.value = 1.0
    if processed_count_label is not None:
        processed_count_label.text = f"Processed: {processed} / {total}"
    if percent_label is not None:
        percent_label.text = '100%'
    ui.notify(f"Finished processing {processed} numbers.", type="info")

    def show_done_dialog():
        with ui.dialog() as d, ui.card().classes('q-pa-md').style('min-width:360px;max-width:520px'):
            ui.label('Completed').classes('text-h6 q-mb-xs')
            ui.label(f'All contacts are processed ({processed} of {total}).').classes('text-body1')
            ui.button('OK', on_click=d.close).classes('q-mt-md bg-primary text-white')
        d.open()
    show_done_dialog()

# ---------------- Controls ----------------
def start_sending():
    global sending, paused
    if not uploaded_excel_content:
        ui.notify('Please upload an Excel file first.', type='negative')
        return
    if sending:
        try:
            ui.run_javascript("""
                (function(){
                    const el = document.querySelector('[data-progress-anchor="1"]');
                    if (!el) return;
                    el.scrollIntoView({behavior:'smooth', block:'center'});
                    const original = el.style.boxShadow;
                    el.style.boxShadow = '0 0 0 3px rgba(25,118,210,.5)';
                    setTimeout(()=>{ el.style.boxShadow = original; }, 1000);
                })();
            """)
        except Exception:
            pass
        return
    try:
        wait_time_seconds = int(wait_time_input.value)
    except Exception:
        wait_time_seconds = 20
    try:
        delay_seconds = int(delay_input.value)
    except Exception:
        delay_seconds = 40

    if progress is not None:
        progress.value = 0
    if percent_label is not None:
        percent_label.text = '0%'
    if processed_count_label is not None:
        processed_count_label.text = "Processed: 0"

    sending = True
    paused = False

    threading.Thread(
        target=send_all_pywhatkit,
        args=(country_code.value, uploaded_excel_content, wait_time_seconds, delay_seconds),
        daemon=True
    ).start()

def pause_sending():
    global paused
    if sending and not paused:
        paused = True
        ui.notify("Paused.", type="warning")

def resume_sending():
    global paused
    if sending and paused:
        paused = False
        ui.notify("Resumed.", type="positive")

def refresh_session():
    global results, uploaded_excel_content, uploaded_contacts_df, filtered_df, sending, paused, current_idx
    results.clear()
    uploaded_excel_content = None
    uploaded_contacts_df = None
    filtered_df = None
    sending = False
    paused = False
    current_idx = -1

    if progress is not None:
        progress.value = 0
    if processed_count_label is not None:
        processed_count_label.text = "Processed: 0"
    if percent_label is not None:
        percent_label.text = '0%'
    if table is not None:
        table.rows = []
        table.update()
    if uploader is not None:
        uploader.reset()
        uploader.value = None
        uploader.update()
    if search_input is not None:
        search_input.value = ''
        search_input.update()
    if search_field_select is not None:
        search_field_select.options = ['Seq']
        search_field_select.value = 'Seq'
        search_field_select.update()
    ui.notify("Session cleared. Ready for new upload.", type="info")

def file_uploaded(files):
    global uploaded_excel_content, uploaded_contacts_df, filtered_df, results, table
    f = files[0] if isinstance(files, list) else files
    if hasattr(f, "content"):
        content = f.content.read() if hasattr(f.content, "read") else f.content
        uploaded_excel_content = content
    else:
        uploaded_excel_content = f.read() if hasattr(f, "read") else f

    results.clear()
    uploaded_contacts_df = None
    filtered_df = None

    if uploaded_excel_content:
        try:
            df = pd.read_excel(BytesIO(uploaded_excel_content))
            uploaded_contacts_df = df.copy()
            filtered_df = uploaded_contacts_df.copy()

            update_search_fields_options()
            update_variables_ui()

            n_contacts = len(df)
            ui.notify(f"Uploaded: {n_contacts} contacts.", type='positive', position='top')
            apply_filter()
            refresh_table()
        except Exception as e:
            uploaded_contacts_df = None
            filtered_df = None
            refresh_table()
            ui.notify(f"File uploaded, but could not preview: {e}", type='warning')
    else:
        uploaded_contacts_df = None
        filtered_df = None
        refresh_table()
        ui.notify("Upload failed -- no file content.", type="negative")

def update_search_fields_options():
    if uploaded_contacts_df is not None and search_field_select is not None:
        cols = list(uploaded_contacts_df.columns)
        preferred_order = []
        for cand in ['Phone', 'Number', 'Message', 'Name']:
            if cand in cols:
                preferred_order.append(cand)
                cols.remove(cand)
        options = ['Seq'] + preferred_order + cols
        search_field_select.options = options
        if 'Phone' in options:
            search_field_select.value = 'Phone'
        elif 'Number' in options:
            search_field_select.value = 'Number'
        else:
            search_field_select.value = 'Seq'
        search_field_select.update()

def update_variables_ui():
    if variables_container is None:
        return
    variables_container.clear()
    if uploaded_contacts_df is None or uploaded_contacts_df.empty:
        with variables_container:
            ui.label('Upload an Excel file to see variables.').classes('text-caption text-grey')
        return

    cols = list(uploaded_contacts_df.columns)
    with variables_container:
        ui.label('Available Variables (click to insert):').classes('text-subtitle2')
        with ui.row().classes('q-gutter-xs q-mt-xs').style('flex-wrap: wrap'):
            for c in cols:
                is_phone = c.lower().strip() in {'phone', 'phonenumber', 'number'}
                placeholder = ' {{phone}} ' if is_phone else f' {{{{ {c} }}}} '
                def make_handler(ph=placeholder):
                    return lambda: insert_placeholder_at_caret_exact(ph)
                ui.button(c, on_click=make_handler(), color='primary').props('flat dense')

# ============================ UI Layout ============================
# Header centered
with ui.card().tight().classes('shadow-4 q-pa-lg q-mb-lg').style('display:flex; justify-content:center; text-align:center;'):
    with ui.column().classes('items-center'):
        ui.label('WhatsApp Broadcast Automation').classes('text-h4')
        ui.label('Send WhatsApp messages in bulk. developed by Hossam Zein').classes('text-body1 text-grey-7')

# TOP ROW: Upload & Settings | Message Settings | Controls
with ui.row().classes('q-gutter-md items-stretch'):
    # Upload & Settings
    with ui.card().tight().classes('shadow-2 q-pa-md').style('min-width:320px; max-width:400px; flex:0 0 auto; align-self:stretch'):
        ui.label('Upload & Settings').classes('text-h6')
        with ui.element('div').style('display:block; width:80%; max-width:260px; min-width:180px'):
            uploader = ui.upload(label='Upload contacts.xlsx').props('flat').classes('q-mb-sm')
            uploader.on_upload(file_uploaded)
        ui.label('Excel must have “Phone/Number” and “Message” columns.').classes('text-caption text-grey q-mt-xs')

    # Message Settings
    with ui.card().tight().classes('shadow-2 q-pa-md').style('width: 680px; flex:0 0 auto; align-self:stretch'):
        ui.label('Message Settings').classes('text-h6')
        message_source_select = ui.select(
            ['Message Column', 'Custom Text'],
            value='Message Column',
            label='Use message from'
        ).props('outlined dense').classes('q-mb-sm')
        ui.label('Note: Do not touch browser during sending').classes('text-negative text-caption q-mb-sm')
        with ui.row().classes('q-gutter-sm'):
            country_code = ui.input('Country Code', value='+20').props('outlined dense').style('min-width:110px; max-width:140px')
            wait_time_input = ui.input('Delay after open (sec)', value='20').props('outlined dense type=number min=1').style('min-width:160px; max-width:200px')
            delay_input = ui.input('Delay between messages (sec)', value='40').props('outlined dense type=number min=1').style('min-width:190px; max-width:230px')
        ui.space().style('height: 8px;')
        custom_message_box = ui.textarea(
            label='Custom Message (supports {{ColumnName}}; {{Phone}}/{{phone}} use normalized phone)',
            value='Hello {{Name}}, your phone is {{phone}}.'
        ).props('outlined autogrow').style('width:100%; min-height: 100px;')
        ui.separator().classes('q-my-sm')
        variables_container = ui.element('div')

    # Controls: strictly horizontal, no wrapping
    with ui.card().tight().classes('shadow-2 q-pa-sm').style('min-width:540px; max-width:560px; flex:0 0 auto; align-self:stretch'):
        ui.label('Controls').classes('text-h6 q-mb-xs')
        with ui.row().classes('q-gutter-xs items-center no-wrap').style('flex-wrap: nowrap; width:100%'):
            ui.button('Start', on_click=start_sending).classes('bg-primary text-white').props('dense')
            ui.button('Pause', on_click=pause_sending).classes('bg-grey-2 text-black').props('dense')
            ui.button('Resume', on_click=resume_sending).classes('bg-green text-white').props('dense')
            ui.button('Reset', on_click=refresh_session).classes('bg-grey-4 text-black').props('dense')
            # spacer pushes the processed label to the far right in the same line
            ui.element('div').style('flex:1')
            processed_count_label = ui.label("Processed: 0").classes('text-caption text-blue-grey-8')

# Standalone progress line (bar + percentage)
with ui.row().classes('items-center q-gutter-sm q-mt-md justify-start').props('data-progress-anchor=1').style('max-width:98vw;'):
    progress = ui.linear_progress().style('min-width:260px; max-width:600px; width:40vw')
    progress.value = 0
    percent_label = ui.label('0%').classes('text-body2 text-blue-grey-8')

# Search: single-line
with ui.card().tight().classes('shadow-2 q-pa-md q-mt-md').style('max-width:98vw;'):
    with ui.row().classes('items-center q-gutter-sm'):
        ui.label('Search').classes('text-h6 q-mr-sm')
        search_field_select = ui.select(options=['Seq'], value='Seq', label='Field').props('outlined dense').style('min-width:140px')
        search_input = ui.input(label='Search').props('outlined dense clearable').on('change', lambda e: apply_filter()).style('min-width:220px')
        ui.button('Clear Filter', on_click=clear_filter).classes('bg-grey-3 text-black')

# Contacts table
with ui.card().tight().classes('shadow-3 q-pa-lg q-mt-md').style('max-width:98vw;overflow-x:auto'):
    ui.label('Contacts List').classes('text-h6 q-mb-xs')
    table = ui.table(
        columns=[{'name': 'Seq', 'label': 'Seq', 'field': 'Seq'}],
        rows=[],
        row_key='Seq'
    ).classes('q-mt-md bg-blue-grey-1 q-table--dense').props('wrap-cells')

# Background refresher
threading.Thread(target=poll_results, daemon=True).start()

ui.run()
