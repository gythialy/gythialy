#!/usr/bin/python
# -*- coding: utf-8 -*-

import codecs
import xml.etree.ElementTree as ET
import requests

r = requests.get("https://gythialy.github.io/atom.xml", timeout=10)
r.encoding = 'utf-8'
feed = r.text
root = ET.fromstring(feed)
nsfeed = {'nsfeed': 'http://www.w3.org/2005/Atom'}
with codecs.open('README.md', 'w', 'utf-8') as f:
    f.write(r'''
## Hi there 👋

- 🔭 I’m currently working on Java/Kotlin and Golang
- 🌱 I’m currently learning [Swift](https://swift.org/) and [Rust](https://github.com/rust-lang/rust)

## Latest blog posts
''')
    for entry in root.findall('nsfeed:entry', nsfeed)[:5]:
        text = entry.find('nsfeed:title', nsfeed).text
        url = entry.find('nsfeed:link', nsfeed).attrib['href']
        published = entry.find('nsfeed:published', nsfeed).text[:10]
        f.write(f"- {published} [{text}]({url})\n")

    f.write('''
[>>> More blog posts](https://gythialy.github.io/)
## Statistics

<!-- Your github readme stats
The official github-readme-stats demo (github-readme-stats.vercel.app) is
paused by Vercel, use github-profile-summary-cards instead:
https://github.com/vn7n24fzkq/github-profile-summary-cards
Light theme: github / dark theme: apprentice
-->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github-profile-summary-cards.vercel.app/api/cards/stats?username=gythialy&amp;theme=apprentice" />
  <img width="55%" align="right" alt="Goren's github stats" src="https://github-profile-summary-cards.vercel.app/api/cards/stats?username=gythialy&amp;theme=github" />
</picture>
<p>
  <!-- Your languages and tools. Be careful with the alignment. 
  You can use this sites to get logos: https://www.vectorlogo.zone or https://simpleicons.org/
  -->
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/java/java-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/kotlinlang/kotlinlang-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/android/android-ar21.svg"></code>
  <br />
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/dotnet/dotnet-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/golang/golang-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/nodejs/nodejs-ar21.svg"></code>
  <br />
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/docker/docker-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/kubernetes/kubernetes-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/traefikio/traefikio-ar21.svg"></code>
  <br />
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/git-scm/git-scm-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/jetbrains/jetbrains-ar21.svg"></code>
  <code><img width="10%" src="https://www.vectorlogo.zone/logos/cloudflare/cloudflare-ar21.svg"></code>
</p>

''')
