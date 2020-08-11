#!/usr/bin/python
# -*- coding: utf-8 -*-

import requests
import xml.etree.ElementTree as ET

feed = requests.get('https://gythialy.github.io/atom.xml').text
root = ET.fromstring(feed)
nsfeed = {'nsfeed': 'http://www.w3.org/2005/Atom'}
with open('README.md', 'w') as f:
    f.write(r'''
## Hi there 👋

- 🔭 I’m currently working on [@QLC Chain](https://github.com/qlcchain)
- 🌱 I’m currently learning [Rust](https://github.com/rust-lang/rust)

## Latest blog posts
''')
    for entry in root.findall('nsfeed:entry', nsfeed)[:5]:
        text = entry.find('nsfeed:title', nsfeed).text
        url = entry.find('nsfeed:link', nsfeed).attrib['href']
        published = entry.find('nsfeed:published', nsfeed).text[:10]
        f.write('- {} [{}]({})\n'.format(published, text, url))

    f.write('''
[>>> More blog posts](https://gythialy.github.io/)
## Statistics
![Goren's github stats](https://github-readme-stats.vercel.app/api?username=gythialy&count_private=true&show_icons=true)
''')