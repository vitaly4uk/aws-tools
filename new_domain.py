#! /usr/bin/python2.7
# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
import jinja2
import string
import io
import os
import random
import re
import argparse
import subprocess
import sys


def prompt_sudo():
    ret = 0
    if os.geteuid() != 0:
        os.environ['SUDO_USER'] = os.getenv('USER')
        msg = "[sudo] password for %u:"
        ret = subprocess.check_call("sudo -v -p '%s'" % msg, shell=True)
    return ret

parser = argparse.ArgumentParser(description='Create config files and start new project. Should be started in project direcrory.')
parser.add_argument('domain', help='Domain name. Example: example.com')
parser.add_argument('--sql', help='SQL file name with DB. Example: example_com.sql')
parser.add_argument('-v', '--version', action='version', version='%(prog)s 0.3')
args = parser.parse_args()

if not prompt_sudo() == 0:
    print('Wrong username or password', file=sys.stderr)
    exit(1)

available_sites_path = '/etc/nginx/sites-available'
enabled_sites_path = '/etc/nginx/sites-enabled'
supervisor_conf_path = '/etc/supervisor/conf.d'
start_port = 8000
root = os.getcwd()
output_file_path = available_sites_path if os.path.exists(available_sites_path) else root
check_port_path = enabled_sites_path if os.path.exists(enabled_sites_path) else root
output_supervisor_path = supervisor_conf_path if os.path.exists(supervisor_conf_path) else root

# Check if we are in some project root directory
if not os.path.exists('./manage.py'):
    print('It is not a project directory', file=sys.stderr)
    exit(1)

# Create virtual environment
if not os.path.exists('./venv'):
    print('Creating virtual environment...')
    subprocess.check_call('virtualenv venv', shell=True)
    subprocess.check_call('./venv/bin/pip install -r requirements.txt', shell=True)

if not os.path.exists('logs'):
    print('Creating logs directory...')
    os.mkdir('logs')

if os.path.exists('/home/ubuntu/mysql_pass'):
    print('Creating MySQL database...')
    mysql_user, mysql_pass = open('/home/ubuntu/mysql_pass').read().strip().split(':')
    sql_name = args.domain.encode('idna').replace('.', '_').replace('-', '_')
    if len(sql_name) > 16:
        sql_name = sql_name[:12] + ''.join(random.choice(string.ascii_uppercase + string.digits) for i in range(4))
    kwargs = {
        'sql_name': sql_name,
        'mysql_user': mysql_user,
        'mysql_pass': mysql_pass,
        'create_db_sql': "CREATE DATABASE {sql_name} CHARACTER SET utf8 COLLATE utf8_general_ci;".format(sql_name=sql_name),
        'create_user_sql': "GRANT ALL PRIVILEGES ON {sql_name}.* To '{sql_name}'@'localhost' IDENTIFIED BY '{sql_name}';".format(sql_name=sql_name),
    }

    subprocess.check_call('echo "{create_db_sql}" | mysql -uroot -p{mysql_pass}'.format(**kwargs), shell=True)
    subprocess.check_call('echo "{create_user_sql}" | mysql -uroot -p{mysql_pass}'.format(**kwargs), shell=True)
    if args.sql:
        kwargs.update({
            'sql_file': args.sql,
        })
        subprocess.check_call('mysql -uroot -p{mysql_pass} {sql_name} < {sql_file}'.format(**kwargs), shell=True)

    print('MySQL user password and database are {sql_name}'.format(sql_name=sql_name))

# Find first available port
for file_name in os.listdir(check_port_path):
    print('Finding port number...')
    full_file_name = os.path.realpath(os.path.join(check_port_path, file_name))
    if os.path.isfile(full_file_name):
        with io.open(full_file_name, 'r', encoding='utf-8') as conf_file:
            try:
                for line in conf_file.readlines():
                    m = re.search('(?<=proxy_pass http://127.0.0.1:)\d+', line)
                    if m is not None:
                        port = int(m.group(0))
                        if port > start_port:
                            start_port = port
            except UnicodeDecodeError:
                continue
start_port += 1
print('PORT: {port}'.format(port=start_port))


# Prepare nginx config
print('Configure nginx...')
template_loader = jinja2.FileSystemLoader([available_sites_path, root])
template_env = jinja2.Environment(loader=template_loader)
template = template_env.get_or_select_template(['template', 'template_nginx'])


template_vars = {
        'domain': args.domain,
        'root': root,
        'port': start_port,
        'user': os.getenv('SUDO_USER'),
        }

with io.open(os.path.join(output_file_path, args.domain), 'w') as tmpl:
    tmpl.write(template.render(template_vars))

with io.open(os.path.join(root, '.port'), 'w') as port_file:
    port_file.write('PORT={port}'.format(port=start_port))

symlink_path = os.path.join(enabled_sites_path, args.domain)
if not os.path.exists(symlink_path):
    os.symlink(os.path.join(output_file_path, args.domain), symlink_path)


# Prepare supervisor config
print('Configure supervisor...')
template_loader = jinja2.FileSystemLoader([supervisor_conf_path, root])
template_env = jinja2.Environment(loader=template_loader)
template = template_env.get_or_select_template(['template', 'template_supervisor'])

with io.open(os.path.join(output_supervisor_path, args.domain + '.conf'), 'w') as tmpl:
    tmpl.write(template.render(template_vars))


# Restart servers
print('Restarting services...')
subprocess.check_call('sudo supervisorctl reload', shell=True)
subprocess.check_call('sudo service nginx restart', shell=True)