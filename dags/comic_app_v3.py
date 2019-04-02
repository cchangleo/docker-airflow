import re
import os
import time
import json
import logging
import requests
import pendulum
from lxml import etree
from datetime import datetime, timedelta
##from selenium.webdriver.chrome.options import Options
##from webdriver_manager.chrome import ChromeDriverManager
from airflow import DAG
from airflow.operators.python_operator import PythonOperator, BranchPythonOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.slack_operator import SlackAPIPostOperator
from airflow.operators.latest_only_operator import LatestOnlyOperator



##driver = webdriver.Chrome(chrome_options=chrome_options)
##driver = webdriver.Chrome('/root/.wdm/chromedriver/2.46/linux64/chromedrive',chrome_options=chrome_options)
##driver = webdriver.Chrome(executable_path= r'/usr/bin/chromedriver', chrome_options=chrome_options)

local_tz = pendulum.timezone("Asia/Taipei")




default_args = {
    'owner': 'Leo',
    'start_date': datetime(2019, 3, 1, 0, 0),
    'schedule_interval': '@daily',
    'retries': 2,
    'retry_delay': timedelta(minutes=1)
}

comic_page_template = 'https://www.cartoonmad.com/comic/{}.html'

def process_metadata(mode, **context):

    file_dir = os.path.dirname(__file__)
    metadata_path = os.path.join(file_dir, '/usr/local/airflow/data/comic.json')
    if mode == 'read':
        with open(metadata_path, 'r') as fp:
            metadata = json.load(fp)
            print("Read History loaded: {}".format(metadata))
            return metadata
    elif mode == 'write':
        print("Saving latest comic information..")
        _, all_comic_info = context['task_instance'].xcom_pull(task_ids='check_comic_info')

        # update to latest chapter
        for comic_id, comic_info in dict(all_comic_info).items():
            all_comic_info[comic_id]['previous_chapter_num'] = comic_info['latest_chapter_num']

        with open(metadata_path, 'w') as fp:
            json.dump(all_comic_info, fp, indent=2, ensure_ascii=False)


def check_comic_info(**context):
    metadata = context['task_instance'].xcom_pull(task_ids='get_read_history')
    ##driver = webdriver.Chrome(chrome_options=chrome_options)
    #driver = webdriver.Chrome(executable_path=r'/usr/bin/chromedriver', chrome_options=chrome_options)
    ##driver = webdriver.Chrome('/root/.wdm/chromedriver/2.46/linux64/chromedrive',chrome_options=chrome_options)

    ##driver.get('https://www.cartoonmad.com/')
    res = requests.get("https://www.cartoonmad.com/comic/1152.html")
    print("Arrived top page.")
    tree = etree.HTML(res.text)
    results = tree.xpath('//*[@id="info"]//tr/td/a/text()')
    nos = [re.findall("\d+", result) for result in results]
    print('{}'.format(nos))
    get_list = nos[-1]

    all_comic_info = metadata
    anything_new = False
    for comic_id, comic_info in dict(all_comic_info).items():
        comic_name = comic_info['name']
        print("Fetching {}'s chapter list..".format(comic_name))
        comic_id = '1152'
       ##res.get(comic_page_template.format(comic_id))
       ## res = requests.get("https://www.cartoonmad.com/comic/1152.html")
        print("Arrived top page.")
        print('{}'.format(nos))
        latest_chapter_num = (int(get_list[0]))
       ## tree = etree.HTML(res.content)
       ## results = tree.xpath('//*[@id="info"]//tr/td/a/text()')
       ## nos = [re.findall("\d+", result) for result in results]

        ## get the latest chapter number
        ##links = res.find_elements_by_partial_link_text('第')
        ##latest_chapter_num = [int(s) for s in links[-1].text.split() if s.isdigit()][0]
       ## print(nos)
       ## get_list =nos[-1]
       ## latest_chapter_num = (int(get_list[0]))
       

        previous_chapter_num = comic_info['previous_chapter_num']

        all_comic_info[comic_id]['latest_chapter_num'] = latest_chapter_num
        all_comic_info[comic_id]['new_chapter_available'] = latest_chapter_num > previous_chapter_num
        if all_comic_info[comic_id]['new_chapter_available']:
            anything_new = True
            print("There are new chapter for {}(latest: {})".format(comic_name, latest_chapter_num))

    if not anything_new:
        print("Nothing new now, prepare to end the workflow.")

  

    return anything_new, all_comic_info


def decide_what_to_do(**context):
    anything_new, all_comic_info = context['task_instance'].xcom_pull(task_ids='check_comic_info')

    print("跟紀錄比較，有沒有新連載？")
    if anything_new:
        return 'yes_generate_notification'
    else:
        return 'no_do_nothing'


def get_token():
    file_dir = os.path.dirname(__file__)
    token_path = os.path.join(file_dir, '/usr/local/airflow/data/credentials/slack.json')
    with open(token_path, 'r') as fp:
        token = json.load(fp)['token']
        return token


def generate_message(**context):
    _, all_comic_info = context['task_instance'].xcom_pull(task_ids='check_comic_info')

    message = ''
    for comic_id, comic_info in all_comic_info.items():
        if comic_info['new_chapter_available']:
            name = comic_info['name']
            latest = comic_info['latest_chapter_num']
            prev = comic_info['previous_chapter_num']
            message += '{} 最新一話： {} 話（上次讀到：{} 話）\n'.format(name, latest, prev)
            message += comic_page_template.format(comic_id) + '\n\n'

    file_dir = os.path.dirname(__file__)
    message_path = os.path.join(file_dir, '/usr/local/airflow/data/message.txt')
    with open(message_path, 'w') as fp:
        fp.write(message)


def get_message_text():
    file_dir = os.path.dirname(__file__)
    message_path = os.path.join(file_dir, '/usr/local/airflow/data/message.txt')
    with open(message_path, 'r') as fp:
        message = fp.read()

    return message


with DAG('comic_app_v3', default_args=default_args) as dag:

    # define tasks
    latest_only = LatestOnlyOperator(task_id='latest_only')

    get_read_history = PythonOperator(
        task_id='get_read_history',
        python_callable=process_metadata,
        op_args=['read'],
        provide_context=True
    )

    check_comic_info = PythonOperator(
        task_id='check_comic_info',
        python_callable=check_comic_info,
        provide_context=True
    )

    decide_what_to_do = BranchPythonOperator(
        task_id='new_comic_available',
        python_callable=decide_what_to_do,
        provide_context=True
    )

    update_read_history = PythonOperator(
        task_id='update_read_history',
        python_callable=process_metadata,
        op_args=['write'],
        provide_context=True
    )

    generate_notification = PythonOperator(
        task_id='yes_generate_notification',
        python_callable=generate_message,
        provide_context=True
    )

    send_notification = SlackAPIPostOperator(
        task_id='send_notification',
        token=get_token(),
        channel='#airflow_test',
        text=get_message_text(),
        icon_url='http://airbnb.io/img/projects/airflow3.png'
    )

    do_nothing = DummyOperator(task_id='no_do_nothing')

    # define workflow
    latest_only >> get_read_history
    get_read_history >> check_comic_info >> decide_what_to_do
    decide_what_to_do >> generate_notification
    decide_what_to_do >> do_nothing
    generate_notification >> send_notification >> update_read_history
