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
from aws_tools import VERSION


def prompt_sudo():
    ret = 0
    if os.geteuid() != 0:
        os.environ['SUDO_USER'] = os.getenv('USER')
        msg = "[sudo] password for %u:"
        ret = subprocess.check_call("sudo -v -p '%s'" % msg, shell=True)
    return ret


def main():
    parser = argparse.ArgumentParser(
        description='Create config files and start new project. Should be started in project directory.')
    parser.add_argument('domain', help='Domain name. Example: example.com')
    parser.add_argument('--sql', help='SQL file name with DB. Example: example_com.sql')
    parser.add_argument('--python', help='python interpreter path', default='/usr/bin/python')
    parser.add_argument('-d', '--debug', help='Debug mode. Only for local development. No nginx and no supervisor.',
                        action='store_true')
    parser.add_argument('--drop-db', help='Drop database if exist.', action='store_true', dest='drop_db')
    parser.add_argument('-r', '--recreate-settings', help='Recreate local_settings file if exist', dest='recreate', action='store_true')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + '.'.join(map(str, VERSION)))
    args = parser.parse_args()

    if not prompt_sudo() == 0:
        print('Wrong username or password', file=sys.stderr)
        exit(1)

    available_sites_path = '/etc/nginx/sites-available'
    enabled_sites_path = '/etc/nginx/sites-enabled'
    supervisor_conf_path = '/etc/supervisor/conf.d'
    data_files_path = '/var/lib/aws-tools'
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
        subprocess.check_call('virtualenv venv --python={0}'.format(args.python), shell=True)
    subprocess.check_call('./venv/bin/pip install -r requirements.txt', shell=True)

    if not os.path.exists('logs'):
        print('Creating logs directory...')
        os.mkdir('logs')
        os.chown('./logs', int(os.getenv('SUDO_UID')), int(os.getenv('SUDO_GID')))

    if os.path.exists('/root/mysql_pass'):
        print('Creating MySQL database...')
        mysql_user, mysql_pass = open('/root/mysql_pass').read().strip().split(':')
        sql_name = args.domain.encode('idna').replace('.', '_').replace('-', '_')
        if len(sql_name) > 16:
            sql_name = sql_name[:12] + ''.join(random.choice(string.ascii_uppercase + string.digits) for i in range(4))
        kwargs = {
            'domain': args.domain,
            'sql_name': sql_name,
            'mysql_user': mysql_user,
            'mysql_pass': mysql_pass,
            'create_db_sql': "CREATE DATABASE {0} CHARACTER SET utf8 COLLATE utf8_general_ci;".format(sql_name),
            'create_user_sql': "GRANT ALL PRIVILEGES ON {0}.* To '{0}'@'localhost' IDENTIFIED BY '{0}';".format(sql_name),
            'mysql_command': ''.join(['mysql -u{0}'.format(mysql_user), ' -p{0}'.format(mysql_pass) if mysql_pass else ''])
        }

        if args.drop_db:
            print('Drop database {sql_name}'.format(**kwargs))
            subprocess.check_call('echo "DROP DATABASE {sql_name};" | {mysql_command}'.format(**kwargs), shell=True)
        subprocess.check_call('echo "{create_db_sql}" | {mysql_command}'.format(**kwargs), shell=True)
        subprocess.check_call('echo "{create_user_sql}" | {mysql_command}'.format(**kwargs), shell=True)
        if args.sql:
            kwargs.update({
                'sql_file': args.sql,
            })
            subprocess.check_call('{mysql_command} {sql_name} < {sql_file}'.format(**kwargs), shell=True)

        print('MySQL user, password and database are {sql_name}'.format(sql_name=sql_name))

        # Prepare local_settings
        if args.recreate and os.path.exists('local_settings.py'):
            os.remove('local_settings.py')
        if not os.path.exists('local_settings.py'):
            print('Configure local_settings...')
            template_loader = jinja2.FileSystemLoader([data_files_path, root])
            template_env = jinja2.Environment(loader=template_loader)
            template = template_env.get_or_select_template(['template', 'template_settings'])

            with io.open('local_settings.py', 'w') as tmpl:
                tmpl.write(template.render(kwargs))
            os.chown('./local_settings.py', int(os.getenv('SUDO_UID')), int(os.getenv('SUDO_GID')))

    # Find first available port
    if not args.debug:
        ports = []
        print('Finding port number in {0}...'.format(check_port_path))
        for file_name in os.listdir(check_port_path):
            print('in {0}'.format(file_name))
            full_file_name = os.path.realpath(os.path.join(check_port_path, file_name))
            if os.path.isfile(full_file_name):
                with io.open(full_file_name, 'r', encoding='utf-8') as conf_file:
                    try:
                        for line in conf_file.readlines():
                            m = re.search('(?<=proxy_pass http://127.0.0.1:)\d+', line)
                            if m is not None:
                                port = int(m.group(0))
                                ports.append(port)
                    except UnicodeDecodeError:
                        continue
        print(ports)
        while start_port in ports:
            start_port += 1
    print('PORT: {port}'.format(port=start_port))

    # store port number in file .port
    with io.open(os.path.join(root, '.port'), 'w') as port_file:
        port_file.write('PORT={port}'.format(port=start_port))
    os.chown('./.port', int(os.getenv('SUDO_UID')), int(os.getenv('SUDO_GID')))

    if not args.debug:
        # Prepare nginx config
        print('Configure nginx...')
        template_loader = jinja2.FileSystemLoader([data_files_path, available_sites_path, root])
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

        symlink_path = os.path.join(enabled_sites_path, args.domain)
        if not os.path.exists(symlink_path):
            os.symlink(os.path.join(output_file_path, args.domain), symlink_path)

        # Prepare supervisor config
        print('Configure supervisor...')
        template_loader = jinja2.FileSystemLoader([data_files_path, supervisor_conf_path, root])
        template_env = jinja2.Environment(loader=template_loader)
        template = template_env.get_or_select_template(['template', 'template_supervisor'])

        with io.open(os.path.join(output_supervisor_path, args.domain + '.conf'), 'w') as tmpl:
            tmpl.write(template.render(template_vars))

        # Restart servers
        print('Restarting services...')
        subprocess.check_call('sudo supervisorctl reload', shell=True)
        subprocess.check_call('sudo service nginx reload', shell=True)


if __name__ == '__main__':
    main()