try:
    import obspython as obs
except ImportError:
    obs = None

if obs is None:
    # upload video from parameters
    import datetime
    import http.client
    import json
    import os
    import os.path
    import random
    import sys
    import time
    import urllib.error
    import urllib.request

    import httplib2

    import google.oauth2.credentials

    import google_auth_oauthlib.flow

    import googleapiclient.discovery
    import googleapiclient.errors
    import googleapiclient.http


    oauth_client = {
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
        'redirect_uris': ['urn:ietf:wg:oauth:2.0:oob', 'http://localhost'],
    }


    def get_youtube_api(project_id, client_id, client_secret):
        try:
            credentials = google.oauth2.credentials.Credentials.from_authorized_user_file(os.path.join(os.path.dirname(__file__), 'ftc-match-uploader-token.json'))
        except FileNotFoundError:
            client_config = {
                'installed': {
                    **oauth_client,
                    'project_id': project_id,
                    'client_id': client_id,
                    'client_secret': client_secret,
                }
            }
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(client_config, ['https://www.googleapis.com/auth/youtubepartner'])
            credentials = flow.run_local_server()
            with open(os.path.join(os.path.dirname(__file__), 'ftc-match-uploader-token.json'), 'w', encoding='utf-8') as token:
                token.write(credentials.to_json())

        return googleapiclient.discovery.build('youtube', 'v3', credentials=credentials)


    def refresh_credentials(google_project_id, google_client_id, google_client_secret):
        print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Refreshing credentials', file=sys.stderr)

        get_youtube_api(google_project_id, google_client_id, google_client_secret)


    def delete_credentials(_google_project_id, _google_client_id, _google_client_secret):
        print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Deleting stored credentials', file=sys.stderr)

        try:
            os.remove(os.path.join(os.path.dirname(__file__), 'ftc-match-uploader-token.json'))
        except FileNotFoundError:
            print(f'  No stored credentials to delete', file=sys.stderr)


    def upload_video(path, title, google_project_id, google_client_id, google_client_secret, description, category_id, privacy, playlist, toa_key, match):
        print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Uploading match video at "{path}"', file=sys.stderr)

        youtube = get_youtube_api(google_project_id, google_client_id, google_client_secret)

        print(f'  Video title: {title}', file=sys.stderr)
        print(f'  Video description:', file=sys.stderr)
        for line in description.splitlines():
            print('    ' + line, file=sys.stderr)
        print(f'  Video category: {category_id}', file=sys.stderr)
        print(f'  Video privacy: {privacy}', file=sys.stderr)

        request_body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': None,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy
            },
        }

        request = youtube.videos().insert(  # pylint: disable=no-member
            part=','.join(request_body.keys()),
            body=request_body,
            media_body=googleapiclient.http.MediaFileUpload(path, chunksize=-1, resumable=True),
        )

        tries = 1

        response = None
        while response is None:
            try:
                _status, response = request.next_chunk()
            except googleapiclient.errors.HttpError as err:
                if err.resp.status in [500, 502, 503, 504]:
                    if tries >= 10:
                        raise RuntimeError(f'YouTube upload failed after {tries} tries with status code {err.resp.status}') from err

                    time.sleep(random.randint(1, 2 ** tries))
                    tries += 1
                else:
                    raise
            except (httplib2.HttpLib2Error, IOError, http.client.NotConnected, http.client.IncompleteRead, http.client.ImproperConnectionState, http.client.CannotSendRequest, http.client.CannotSendHeader, http.client.ResponseNotReady, http.client.BadStatusLine) as err:
                if tries >= 10:
                    raise RuntimeError(f'YouTube upload failed after {tries} tries with error: {err}') from err

                time.sleep(random.randint(1, 2 ** tries))
                tries += 1

        if 'id' not in response:
            raise RuntimeError(f'YouTube upload failed with unexpected response: {response}')

        video = response['id']
        link = 'https://youtu.be/' + video

        print(f'  YouTube ID: {video}', file=sys.stderr)
        print(f'  YouTube link: {link}', file=sys.stderr)

        if playlist:
            print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Adding to playlist {playlist}', file=sys.stderr)

            request_body = {
                'snippet': {
                    'playlistId': playlist,
                    'resourceId': {
                        'kind': 'youtube#video',
                        'videoId': video,
                    },
                },
            }

            request = youtube.playlistItems().insert(  # pylint: disable=no-member
                part=','.join(request_body.keys()),
                body=request_body,
            )

            try:
                response = request.execute()

                if 'id' in response:
                    print(f'  YouTube Playlist Item ID: {response["id"]}', file=sys.stderr)
                else:
                    print(f'  YouTube playlist insert failed with unexpected response: {response}', file=sys.stderr)
            except googleapiclient.errors.HttpError as err:
                print(f'  YouTube playlist insert failed with status code {err.resp.status}', file=sys.stderr)
        else:
            print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Not adding to a playlist', file=sys.stderr)

        if toa_key:
            print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Adding to The Orange Alliance match {match}', file=sys.stderr)

            toa_headers = {
                'Content-Type': 'application/json',
                'X-Application-Origin': 'OBS FTC Match Uploader',
                'X-TOA-Key': toa_key,
            }

            toa_body = {
                'match_key': match,
                'video_url': link,
            }

            toa_request = urllib.request.Request('https://theorangealliance.org/api/match/video', data=json.dumps(toa_body).encode('utf-8'), headers=toa_headers, method='PUT')

            try:
                with urllib.request.urlopen(toa_request) as toa:
                    response_code = toa.getcode()
                    response = toa.read()

                if response_code != 200:
                    print(f'  The Orange Alliance match video update failed with unexpected status code {response_code} and response: {response}', file=sys.stderr)
            except urllib.error.HTTPError as err:
                print(f'  The Orange Alliance match video update failed with status code {err.code}', file=sys.stderr)

        try:
            os.remove(path)
        except OSError as err:
            raise RuntimeError(f'Error removing video file: {path}') from err


    commands = {
    }


    if len(sys.argv) != 3:
        print(f'This file is intended to be used as an OBS script. Load it up in OBS Studio and use it from there.', file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] not in commands:
        print(f'Unknown command: {sys.argv[1]}', file=sys.stderr)
        sys.exit(1)

    try:
        with open(sys.argv[2], 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except (OSError, ValueError):
        print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Error reading metadata file: {sys.argv[2]}', file=sys.stderr)
        sys.exit(1)

    try:
        commands[sys.argv[1]](**metadata)
    except Exception:  # pylint: disable=broad-exception-caught
        import traceback
        print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Exception occurred for command "{sys.argv[1]}":', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            os.remove(sys.argv[2])
        except OSError:
            print(f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Error removing metadata file: {sys.argv[2]}', file=sys.stderr)
            sys.exit(1)
else:
    # implement OBS-side of the plugin
    import asyncio
    import json
    import os
    import os.path
    import queue
    import re
    import subprocess
    import sys
    import tempfile
    import threading
    import time
    import urllib.error
    import urllib.request

    import websockets.client


    if sys.platform == 'win32':
        python_path = os.path.join(sys.exec_prefix, 'pythonw.exe')
    else:
        python_path = os.path.join(sys.exec_prefix, 'bin', 'python3')


    settings = None  # pylint: disable=invalid-name
    hotkeys = {}  # pylint: disable=invalid-name
    thread = None  # pylint: disable=invalid-name

    comm = None  # pylint: disable=invalid-name
    stop = None  # pylint: disable=invalid-name

    output = None  # pylint: disable=invalid-name
    output_video_encoder = None  # pylint: disable=invalid-name
    output_audio_encoder = None  # pylint: disable=invalid-name
    action = 'none'  # pylint: disable=invalid-name
    children = []

    post_time = -1  # pylint: disable=invalid-name

    msg_mapping = {
        'MATCH_LOAD': 'match_load',
        'SHOW_PREVIEW': 'show_preview',
        'SHOW_RANDOM': 'show_random',
        'SHOW_MATCH': 'show_match',
        'MATCH_START': 'match_start',
        'MATCH_ABORT': 'match_abort',
        'MATCH_COMMIT': 'match_commit',
        'MATCH_POST': 'match_post',
        'MATCH_WAIT': 'match_wait',
        'pong': 'pong'
        # state for an alternative scene between matches - not sent by scorekeeper
    }


    def script_description():
        return '<b>FTC Stream Manager</b><hr/>Automatically switch OBS scenes based on events from the FTCLive scorekeeping software as well as cut and upload FTC matches to YouTube during a stream. Optionally can add those videos to a playlist or add those videos to an event on The Orange Alliance.'


    def script_load(settings_):
        global settings, comm, stop  # pylint: disable=invalid-name

        settings = settings_

        reset_match_info()

        # cross-thread communication
        comm = queue.Queue(32)
        stop = threading.Event()

        # run child reaper every second
        obs.timer_add(check_children, 1000)

        # websocket thread communication checker
        obs.timer_add(check_websocket, 100)

        # connect to scorekeeper websocket
        reconnect_scorekeeper_ws()

        # create recording output
        recreate_recording_output()

        # get saved hotkey data
        hotkey_start = obs.obs_data_get_array(settings, 'hotkey_start')
        hotkey_stop = obs.obs_data_get_array(settings, 'hotkey_stop')
        hotkey_cancel = obs.obs_data_get_array(settings, 'hotkey_cancel')
        hotkey_enable = obs.obs_data_get_array(settings, 'hotkey_enable')
        hotkey_disable = obs.obs_data_get_array(settings, 'hotkey_disable')

        # register hotkeys
        hotkeys['start'] = obs.obs_hotkey_register_frontend('ftc-stream-manager_start', '(FTC) Start recording a match', start_recording)
        hotkeys['stop'] = obs.obs_hotkey_register_frontend('ftc-stream-manager_stop', '(FTC) Stop recording a match and upload to YouTube', stop_recording_and_upload)
        hotkeys['cancel'] = obs.obs_hotkey_register_frontend('ftc-stream-manager_cancel', '(FTC) Stop recording a match but cancel uploading to YouTube', stop_recording_and_cancel)
        hotkeys['enable'] = obs.obs_hotkey_register_frontend('ftc-stream-manager_enable', '(FTC) Enable automatic scene switcher and recorder', enable_switcher)
        hotkeys['disable'] = obs.obs_hotkey_register_frontend('ftc-stream-manager_disable', '(FTC) Disable automatic scene switcher and recorder', disable_switcher)

        # load saved hotkey data
        obs.obs_hotkey_load(hotkeys['start'], hotkey_start)
        obs.obs_hotkey_load(hotkeys['stop'], hotkey_stop)
        obs.obs_hotkey_load(hotkeys['cancel'], hotkey_cancel)
        obs.obs_hotkey_load(hotkeys['enable'], hotkey_enable)
        obs.obs_hotkey_load(hotkeys['disable'], hotkey_disable)

        # release data references
        obs.obs_data_array_release(hotkey_start)
        obs.obs_data_array_release(hotkey_stop)
        obs.obs_data_array_release(hotkey_cancel)
        obs.obs_data_array_release(hotkey_enable)
        obs.obs_data_array_release(hotkey_disable)


    def script_unload():
        obs.timer_remove(check_children)

        # stop websocket thread
        disconnect_scorekeeper_websocket()

        # stop communication checker
        obs.timer_remove(check_websocket)

        # destroy extra video output
        destroy_match_video_output()


    def script_save(settings_):
        # save hotkey data
        hotkey_start = obs.obs_hotkey_save(hotkeys['start'])
        hotkey_stop = obs.obs_hotkey_save(hotkeys['stop'])
        hotkey_cancel = obs.obs_hotkey_save(hotkeys['cancel'])
        hotkey_enable = obs.obs_hotkey_save(hotkeys['enable'])
        hotkey_disable = obs.obs_hotkey_save(hotkeys['disable'])

        # set hotkey data
        obs.obs_data_set_array(settings_, 'hotkey_start', hotkey_start)
        obs.obs_data_set_array(settings_, 'hotkey_stop', hotkey_stop)
        obs.obs_data_set_array(settings_, 'hotkey_cancel', hotkey_cancel)
        obs.obs_data_set_array(settings_, 'hotkey_enable', hotkey_enable)
        obs.obs_data_set_array(settings_, 'hotkey_disable', hotkey_disable)

        # release data references
        obs.obs_data_array_release(hotkey_start)
        obs.obs_data_array_release(hotkey_stop)
        obs.obs_data_array_release(hotkey_cancel)
        obs.obs_data_array_release(hotkey_enable)
        obs.obs_data_array_release(hotkey_disable)


    def script_properties():
        props = obs.obs_properties_create()


        scorekeeper_props = obs.obs_properties_create()
        obs.obs_properties_add_group(props, 'scorekeeper', 'Scorekeeper', obs.OBS_GROUP_NORMAL, scorekeeper_props)

        obs.obs_properties_add_text(scorekeeper_props, 'event_code', 'Event Code', obs.OBS_TEXT_DEFAULT)
        obs.obs_properties_add_text(scorekeeper_props, 'scorekeeper_api', 'Scorekeeper API', obs.OBS_TEXT_DEFAULT)
        obs.obs_properties_add_text(scorekeeper_props, 'scorekeeper_ws', 'Scorekeeper WS', obs.OBS_TEXT_DEFAULT)

        obs.obs_properties_add_button(scorekeeper_props, 'reconnect_scorekeeper_ws', 'Reconnect Scorekeeper WS', reconnect_scorekeeper_ws)
        obs.obs_properties_add_button(scorekeeper_props, 'test_scorekeeper_connection', 'Test Scorekeeper Connection', test_scorekeeper_connection)


        switcher_props = obs.obs_properties_create()
        obs.obs_properties_add_group(props, 'switcher', 'Switcher', obs.OBS_GROUP_NORMAL, switcher_props)
        obs.obs_properties_add_bool(switcher_props, 'switcher_enabled', 'Automatic Switcher')
        obs.obs_properties_add_bool(switcher_props, 'switcher_recording', 'Automatic Recording on Switches')
        obs.obs_properties_add_bool(switcher_props, 'override_non_match_scenes', 'Override Non-Match Scenes')
        obs.obs_properties_add_int(switcher_props, 'match_wait_time', 'Match Post Time to Match Wait', -1, 600, 1)


        def add_scene_to_dropdown(scene, dropdown_property):
            scene_name = obs.obs_source_get_name(scene)
            obs.obs_property_list_add_string(dropdown_property, scene_name, scene_name)
            return True  # Continue enumeration

        scene_props = obs.obs_properties_create()
        obs.obs_properties_add_group(props, 'scene', 'Scenes', obs.OBS_GROUP_NORMAL, scene_props)

        # obs.obs_properties_add_text(scene_props, 'match_load', 'Match Load', obs.OBS_TEXT_DEFAULT)
        dropdown_property = obs.obs_properties_add_list(scene_props, "match_load", "Match Load", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "show_preview", "Show Preview", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "show_random", "Show Random", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "show_match", "Show Match", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "match_start", "Match Start", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "match_abort", "Match Abort", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "match_commit", "Match Commit", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "match_post", "Match Post", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        
        dropdown_property = obs.obs_properties_add_list(scene_props, "match_wait", "Match Wait", obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        scenes = obs.obs_frontend_get_scenes()
        for scene in scenes:
            add_scene_to_dropdown(scene, dropdown_property)
        obs.source_list_release(scenes)
        


        recording_props = obs.obs_properties_create()
        obs.obs_properties_add_group(props, 'recording', 'Recording', obs.OBS_GROUP_NORMAL, recording_props)

        output_resolution_prop = obs.obs_properties_add_list(recording_props, 'output_resolution', 'Output Resolution', obs.OBS_COMBO_TYPE_EDITABLE, obs.OBS_COMBO_FORMAT_STRING)
        output_resolution_options = {'1920x1080', '1280x720'}
        canvas_source = obs.obs_frontend_get_current_scene()
        canvas_width, canvas_height = obs.obs_source_get_width(canvas_source), obs.obs_source_get_height(canvas_source)
        obs.obs_source_release(canvas_source)
        output_resolution_options.add(f'{canvas_width}x{canvas_height}')
        try:
            for resolution in sorted(output_resolution_options, key=lambda res: int(res.split('x', 1)[0]), reverse=True):
                obs.obs_property_list_add_string(output_resolution_prop, resolution, resolution)
        except ValueError:
            print(f'ERROR: Resolution options are malformed')
            print()

        video_encoder_prop = obs.obs_properties_add_list(recording_props, 'video_encoder', 'Video Encoder (H.264)', obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        obs.obs_property_list_add_string(video_encoder_prop, 'x264', 'obs_x264')
        if obs.obs_encoder_get_display_name('jim_nvenc'):
            obs.obs_property_list_add_string(video_encoder_prop, 'NVENC', 'jim_nvenc')
        elif obs.obs_encoder_get_display_name('ffmpeg_nvenc'):
            obs.obs_property_list_add_string(video_encoder_prop, 'NVENC', 'ffmpeg_nvenc')
        if obs.obs_encoder_get_display_name('amd_amf_h264'):
            obs.obs_property_list_add_string(video_encoder_prop, 'AMF', 'amd_amf_h264')
        if obs.obs_encoder_get_display_name('obs_qsv11'):
            obs.obs_property_list_add_string(video_encoder_prop, 'QuickSync', 'obs_qsv11')
        obs.obs_properties_add_int(recording_props, 'video_bitrate', 'Video Bitrate', 0, 24000, 50)
        audio_encoder_prop = obs.obs_properties_add_list(recording_props, 'audio_encoder', 'Audio Encoder (AAC)', obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        obs.obs_property_list_add_string(audio_encoder_prop, 'FFmpeg', 'ffmpeg_aac')
        if obs.obs_encoder_get_display_name('mf_aac'):
            obs.obs_property_list_add_string(audio_encoder_prop, 'MediaFoundation', 'mf_aac')
        if obs.obs_encoder_get_display_name('libfdk_aac'):
            obs.obs_property_list_add_string(audio_encoder_prop, 'Fraunhofer FDK', 'libfdk_aac')
        if obs.obs_encoder_get_display_name('CoreAudio_AAC'):
            obs.obs_property_list_add_string(audio_encoder_prop, 'CoreAudio', 'CoreAudio_AAC')
        obs.obs_properties_add_int(recording_props, 'audio_bitrate', 'Audio Bitrate', 0, 2000, 1)

        obs.obs_properties_add_button(recording_props, 'recreate_recording_output', 'Recreate Recording Output', recreate_recording_output)

        match_props = obs.obs_properties_create()
        obs.obs_properties_add_group(props, 'match', 'Match (Internal Settings)', obs.OBS_GROUP_NORMAL, match_props)

        match_type_prop = obs.obs_properties_add_list(match_props, 'match_type', 'Match Type', obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
        obs.obs_property_list_add_string(match_type_prop, 'Qualification', 'qualification')
        obs.obs_property_list_add_string(match_type_prop, 'Semi-Final', 'semi-final')
        obs.obs_property_list_add_string(match_type_prop, 'Final', 'final')
        obs.obs_properties_add_int(match_props, 'match_pair', 'Match Pair', 1, 2, 1)
        obs.obs_properties_add_int(match_props, 'match_number', 'Match Number', 1, 1000, 1)
        obs.obs_properties_add_int(match_props, 'match_code', 'Match Code', 1, 1000, 1)

        obs.obs_properties_add_button(match_props, 'reset_match_info', 'Reset Match Info', reset_match_info)

        return props


    def script_defaults(settings_):
        obs.obs_data_set_default_string(settings_, 'event_name', 'FTC Test Event')
        obs.obs_data_set_default_string(settings_, 'youtube_description', 'Testing FTC video cutting and uploading during a stream')
        obs.obs_data_set_default_string(settings_, 'youtube_category_id', '28')
        obs.obs_data_set_default_string(settings_, 'youtube_privacy_status', 'private')
        obs.obs_data_set_default_string(settings_, 'youtube_playlist', '')

        obs.obs_data_set_default_string(settings_, 'event_code', 'qcmp')
        obs.obs_data_set_default_string(settings_, 'scorekeeper_api', 'http://localhost/api')
        obs.obs_data_set_default_string(settings_, 'scorekeeper_ws', 'ws://localhost/api/v2/stream/')

        obs.obs_data_set_default_string(settings_, 'toa_key', '')
        obs.obs_data_set_default_string(settings_, 'toa_event', '')

        obs.obs_data_set_default_string(settings_, 'google_project_id', '')
        obs.obs_data_set_default_string(settings_, 'google_client_id', '')
        obs.obs_data_set_default_string(settings_, 'google_client_secret', '')

        obs.obs_data_set_default_bool(settings_, 'switcher_enabled', True)
        obs.obs_data_set_default_bool(settings_, 'switcher_recording', True)
        obs.obs_data_set_default_bool(settings_, 'override_non_match_scenes', False)
        obs.obs_data_set_default_int(settings_, 'match_wait_time', 30)

        # obs.obs_data_set_default_string(settings_, 'show_preview', 'Pit Scoring')
        # obs.obs_data_set_default_string(settings_, 'show_random', 'فيديو تحدي')
        # obs.obs_data_set_default_string(settings_, 'show_match', 'status')
        # obs.obs_data_set_default_string(settings_, 'match_start', 'فيديو الداعمين')
        # obs.obs_data_set_default_string(settings_, 'match_abort', 'Feild Scoring')
        # obs.obs_data_set_default_string(settings_, 'match_commit', 'Pit Scoring')
        # obs.obs_data_set_default_string(settings_, 'match_post', 'فيديو تحدي')
        # obs.obs_data_set_default_string(settings_, 'match_wait', 'status')

        canvas_source = obs.obs_frontend_get_current_scene()
        canvas_width, canvas_height = obs.obs_source_get_width(canvas_source), obs.obs_source_get_height(canvas_source)
        obs.obs_source_release(canvas_source)
        obs.obs_data_set_default_string(settings_, 'output_resolution', f'{canvas_width}x{canvas_height}')
        obs.obs_data_set_default_string(settings_, 'video_encoder', 'obs_x264')
        obs.obs_data_set_default_int(settings_, 'video_bitrate', 2500)
        obs.obs_data_set_default_string(settings_, 'audio_encoder', 'ffmpeg_aac')
        obs.obs_data_set_default_int(settings_, 'audio_bitrate', 192)

        obs.obs_data_set_default_string(settings_, 'match_type', 'qualification')
        obs.obs_data_set_default_int(settings_, 'match_pair', 1)
        obs.obs_data_set_default_int(settings_, 'match_number', 1)
        obs.obs_data_set_default_int(settings_, 'match_code', 1)


    def connect_scorekeeper_websocket():
        global thread  # pylint: disable=invalid-name

        print(f'Connecting to scorekeeper WS')

        if thread and thread.is_alive():
            print(f'WARNING: Scorekeeper WS is already connected')
            print()
            return

        stop.clear()

        print(f'{obs.obs_data_get_string(settings, "scorekeeper_ws")}?code={obs.obs_data_get_string(settings, "event_code")}')
        thread = threading.Thread(target=lambda: asyncio.run(run_websocket(f'{obs.obs_data_get_string(settings, "scorekeeper_ws")}?code={obs.obs_data_get_string(settings, "event_code")}')))
        thread.start()

        print()


    def disconnect_scorekeeper_websocket():
        global thread  # pylint: disable=invalid-name

        print(f'Disconnecting from scorekeeper WS')

        if not thread or not thread.is_alive():
            print(f'WARNING: Scorekeeper WS is already disconnected')
            print()
            return

        stop.set()
        thread.join()

        thread = None

        print()


    def create_match_video_output():
        global output, output_video_encoder, output_audio_encoder  # pylint: disable=invalid-name

        print(f'Creating match video OBS output')

        if output:
            print(f'WARNING: Match video OBS output already exists')
            print()
            return

        # create output for match video files
        output_settings = obs.obs_data_create()
        obs.obs_data_set_bool(output_settings, 'allow_overwrite', True)
        output = obs.obs_output_create('ffmpeg_muxer', 'match_file_output', output_settings, None)
        obs.obs_data_release(output_settings)
        if not output:
            print(f'ERROR: Could not create match video output')
            print()
            return

        # create output video encoder for match video files
        output_video_settings = obs.obs_data_create()
        obs.obs_data_set_string(output_video_settings, 'rate_control', 'CBR')
        obs.obs_data_set_int(output_video_settings, 'bitrate', obs.obs_data_get_int(settings, 'video_bitrate'))
        output_video_encoder = obs.obs_video_encoder_create(obs.obs_data_get_string(settings, 'video_encoder'), 'match_video_encoder', output_video_settings, None)
        obs.obs_data_release(output_video_settings)
        if not output_video_encoder:
            print(f'ERROR: Could not create match video encoder')
            destroy_match_video_output()
            return
        if not obs.obs_encoder_get_codec(output_video_encoder):
            print(f'ERROR: Invalid codec for match video encoder')
            destroy_match_video_output()
            return
        output_video_resolution = re.fullmatch(r'(\d{1,5})x(\d{1,5})', obs.obs_data_get_string(settings, 'output_resolution'))
        if output_video_resolution:
            try:
                output_video_width, output_video_height = map(int, output_video_resolution.groups())
                if output_video_width < 8 or output_video_width > 16384 or output_video_height < 8 or output_video_height > 16384:
                    raise ValueError()
            except ValueError:
                print(f'ERROR: Invalid resolution for match video encoder')
                destroy_match_video_output()
                return
            obs.obs_encoder_set_scaled_size(output_video_encoder, output_video_width, output_video_height)
        obs.obs_encoder_set_video(output_video_encoder, obs.obs_get_video())
        if not obs.obs_encoder_video(output_video_encoder):
            print(f'ERROR: Could not set video handler')
            destroy_match_video_output()
            return
        obs.obs_output_set_video_encoder(output, output_video_encoder)
        if not obs.obs_output_get_video_encoder(output):
            print(f'ERROR: Could not set video encoder to output')
            destroy_match_video_output()
            return

        # create output audio encoder for match video files
        output_audio_settings = obs.obs_data_create()
        obs.obs_data_set_string(output_audio_settings, 'rate_control', 'CBR')
        obs.obs_data_set_int(output_audio_settings, 'bitrate', obs.obs_data_get_int(settings, 'audio_bitrate'))
        output_audio_encoder = obs.obs_audio_encoder_create(obs.obs_data_get_string(settings, 'audio_encoder'), 'match_audio_encoder', output_audio_settings, 0, None)
        obs.obs_data_release(output_audio_settings)
        if not output_audio_encoder:
            print(f'ERROR: Could not create match audio encoder')
            destroy_match_video_output()
            return
        if not obs.obs_encoder_get_codec(output_audio_encoder):
            print(f'ERROR: Invalid codec for match audio encoder')
            destroy_match_video_output()
            return
        obs.obs_encoder_set_audio(output_audio_encoder, obs.obs_get_audio())
        if not obs.obs_encoder_audio(output_audio_encoder):
            print(f'ERROR: Could not set audio handler')
            destroy_match_video_output()
            return
        obs.obs_output_set_audio_encoder(output, output_audio_encoder, 0)
        if not obs.obs_output_get_audio_encoder(output, 0):
            print(f'ERROR: Could not set audio encoder to output')
            destroy_match_video_output()
            return

        # set handler for output signals
        handler = obs.obs_output_get_signal_handler(output)
        obs.signal_handler_connect(handler, 'stop', stop_recording_action)

        print()


    def destroy_match_video_output():
        global output, output_video_encoder, output_audio_encoder  # pylint: disable=invalid-name

        print(f'Destroying match video OBS output')

        if not output:
            print(f'WARNING: Match video OBS output does not exist')
            print()
            return

        # release output (which should then be garbage collected)
        obs.obs_output_release(output)
        output = None
        obs.obs_encoder_release(output_video_encoder)
        output_video_encoder = None
        obs.obs_encoder_release(output_audio_encoder)
        output_audio_encoder = None

        print()


    def check_children():
        reaped = []
        for child, log in children:
            if child.poll() is not None:
                reaped.append(child)

                if child.returncode != 0:
                    print(f'ERROR: Subprocess exited with code {child.returncode}: {child.args}')
                    with open(log, 'r', encoding='utf-8') as logf:
                        print('\n'.join(f'  {line}' for line in logf.read().splitlines()))
                    print()
                try:
                    os.remove(log)
                except OSError:
                    print(f'WARNING: Failed to remove log file: {log}')

        if reaped:
            children[:] = ((child, log) for child, log in children if child not in reaped)


    def check_websocket():
        global thread, post_time  # pylint: disable=invalid-name

        if not obs.obs_data_get_bool(settings, 'switcher_enabled'):
            return

        if thread and not thread.is_alive():
            # thread died and needs to be retried or cleaned up
            print(f'ERROR: Connection to scorekeeper WS failed')
            print()

            # disable switcher to prevent failure spam
            stop.set()
            thread = None

            # no return to let queue continue to be cleared since we are enabled

        try:
            while True:
                if obs.obs_data_get_int(settings, 'match_wait_time') >= 0 and post_time >= 0 and time.time() >= post_time + obs.obs_data_get_int(settings, 'match_wait_time'):
                    # still in match post timer has been reached - set to match wait
                    scene = 'match_wait'
                else:
                    # check websocket for events
                    msg = comm.get_nowait()
                    try:
                        scene = msg_mapping[msg['updateType']]
                    except KeyError:
                        print(f'WARNING: Unknown WS match event type {msg["updateType"]}')
                        print()
                        continue

                # reset match post time (it gets overwritten again in conditional if transitioning to match_wait)
                post_time = -1
                if scene == 'pong':
                    # ignore pong events
                    continue
                print(f'Got WS match event: {scene}')
                if scene == 'match_load':
                    # stop recording last match if it is still recording
                    if obs.obs_output_active(output):
                        stop_recording_and_upload()
                elif scene in ['show_preview', 'show_random', 'show_match', 'match_start']:
                    # start recording if not already recording (e.g. if preview or match was shown more than once)
                    if obs.obs_data_get_bool(settings, 'switcher_recording') and not obs.obs_output_active(output):
                        start_recording()
                    # start recording if not already recording (e.g. if preview or match was shown more than once)
                elif scene == 'match_post':
                    # record when a scene was switched to match post
                    post_time = time.time()
                elif scene == 'match_wait':
                    if obs.obs_output_active(output):
                        stop_recording_and_upload()
                elif scene == 'match_abort':
                    if obs.obs_output_active(output):
                        stop_recording_and_cancel()

                # bail if not currently on a recognized scene
                current_scene = obs.obs_frontend_get_current_scene()
                current_scene_name = obs.obs_source_get_name(current_scene)
                obs.obs_source_release(current_scene)
                print("check this:")
                print("check this:")
                print("check this:")
                if not obs.obs_data_get_bool(settings, 'override_non_match_scenes') and current_scene_name not in map(lambda scene: obs.obs_data_get_string(settings, scene), msg_mapping.values()):
                    print(f'WARNING: Ignoring scorekeeper event because the current scene is unrecognized and overriding unrecognized scenes is disabled')
                    print()
                    continue

                print(f'Switching scene to {obs.obs_data_get_string(settings, scene)}')
                print(f'scene = {scene}')
                print()

                # find and set the current scene based on websocket or wait set above
                sources = obs.obs_frontend_get_scenes()
                for source in sources:
                    if obs.obs_source_get_name(source) == obs.obs_data_get_string(settings, scene):
                        obs.obs_frontend_set_current_scene(source)
                        break
                else:
                    print(f'WARNING: Could not find scene {obs.obs_data_get_string(settings, scene)}')
                    print()
                obs.source_list_release(sources)
        except queue.Empty:
            pass


    async def run_websocket(uri):
        async with websockets.client.connect(uri) as websocket:
            # thread kill-switch check
            while not stop.is_set():
                try:
                    # try to get something from websocket and put it in queue for main thread (dropping events when queue is full)
                    messagefromWS = await asyncio.wait_for(websocket.recv(), 0.2)
                    try:
                        comm.put_nowait(json.loads(messagefromWS))
                    except :
                        comm.put_nowait(json.loads('{"updateType": "pong"}'))
                except (asyncio.TimeoutError, queue.Full):
                    pass


    def get_match_name():
        match_type = obs.obs_data_get_string(settings, 'match_type')
        if match_type == 'final':
            return f'Finals Match {obs.obs_data_get_int(settings, "match_number")}'
        elif match_type == 'semi-final':
            return f'Semifinals {obs.obs_data_get_int(settings, "match_pair")} Match {obs.obs_data_get_int(settings, "match_number")}'
        elif match_type == 'qualification':
            return f'Qualifications Match {obs.obs_data_get_int(settings, "match_number")}'
        else:
            return f'Match {obs.obs_data_get_int(settings, "match_number")}'


    def reset_match_info(_prop=None, _props=None):
        obs.obs_data_set_string(settings, 'match_type', 'qualification')
        obs.obs_data_set_int(settings, 'match_pair', 1)
        obs.obs_data_set_int(settings, 'match_number', 1)
        obs.obs_data_set_int(settings, 'match_code', 1)

        print(f'Match info reset')
        print()


    def test_scorekeeper_connection(_prop=None, _props=None):
        try:
            with urllib.request.urlopen(f'{obs.obs_data_get_string(settings, "scorekeeper_api")}/v1/events/{obs.obs_data_get_string(settings, "event_code")}/', timeout=1) as scorekeeper:
                scorekeeper_code = scorekeeper.getcode()
                event_code = json.load(scorekeeper)['eventCode']
        except urllib.error.HTTPError as err:
            scorekeeper_code = err.code
        except (IOError, KeyError):
            scorekeeper_code = -1

        if scorekeeper_code == 200 and event_code == obs.obs_data_get_string(settings, 'event_code'):
            print(f'Successfully connected to scorekeeper API')
        elif scorekeeper_code == 404:
            print(f'Connected to scorekeeper API but the event code was not found')
        elif scorekeeper_code >= 400:
            print(f'Connected to scorekeeper API but encountered unexpected status code {scorekeeper_code}')
        else:
            print(f'Failed to connect to scorekeeper API')

        print()


    def reconnect_scorekeeper_ws(_prop=None, _props=None):
        if thread and thread.is_alive():
            disconnect_scorekeeper_websocket()
        if obs.obs_data_get_bool(settings, 'switcher_enabled'):
            connect_scorekeeper_websocket()




    def recreate_recording_output(_prop=None, _props=None):
        if output:
            destroy_match_video_output()
        create_match_video_output()


    def stop_recording_action(calldata):
        global action  # pylint: disable=invalid-name

        signal_output = obs.calldata_ptr(calldata, 'output')
        code = obs.calldata_int(calldata, 'code')

        if signal_output != output:
            print(f'WARNING: Match stop recording signal called with non-match output')
            print()
            return

        output_settings = obs.obs_output_get_settings(output)
        video_path = obs.obs_data_get_string(output_settings, 'path')
        obs.obs_data_release(output_settings)

        if code != 0:  # OBS_OUTPUT_SUCCESS == 0
            print(f'ERROR: Match recording not stopped successfully')
            print()
            return

        if action == 'cancel':
            print(f'Cancelling upload for {get_match_name()} at "{video_path}"')
            print()

        action = 'none'


    def start_recording(pressed=False):
        if pressed:
            return
        if obs.obs_output_active(output):
            print(f'WARNING: Currently recording {get_match_name()}')
            print()
            return

        match_path = "C:\\Users\\melkmeshi\\Videos\\" + get_match_name() + ".mkv"
        output_settings = obs.obs_data_create()
        obs.obs_data_set_string(output_settings, 'path', f'{match_path}')
        obs.obs_output_update(output, output_settings)
        obs.obs_data_release(output_settings)

        if not obs.obs_output_start(output):
            print(f'ERROR: Could not start match recording: {obs.obs_output_get_last_error(output) or "Unknown error"}')
            print()
            return


        print(f'Recording started for {get_match_name()}')


    def stop_recording_and_upload(pressed=False):
        global action  # pylint: disable=invalid-name

        if pressed:
            return

        if not obs.obs_output_active(output):
            print(f'WARNING: Not currently recording a match')
            print()
            return

        action = 'upload'

        obs.obs_output_stop(output)

        print(f'Recording stopping for {get_match_name()}')


    def stop_recording_and_cancel(pressed=False):
        global action  # pylint: disable=invalid-name

        if pressed:
            return

        if not obs.obs_output_active(output):
            print(f'WARNING: Not currently recording a match')
            print()
            return

        action = 'cancel'

        obs.obs_output_stop(output)

        print(f'Recording stopping for {get_match_name()}')


    def enable_switcher(pressed=False):
        if pressed:
            return

        obs.obs_data_set_bool(settings, 'switcher_enabled', True)

        print(f'Enabling scene switcher')

        if thread and thread.is_alive():
            disconnect_scorekeeper_websocket()

        connect_scorekeeper_websocket()


    def disable_switcher(pressed=False):
        if pressed:
            return

        print(f'Disabling scene switcher')

        obs.obs_data_set_bool(settings, 'switcher_enabled', False)

        if thread and thread.is_alive():
            disconnect_scorekeeper_websocket()
