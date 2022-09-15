# textbooks_match.py
import sys
import os
import requests
import lxml.html
from lxml.cssselect import CSSSelector
import logging
import csv
import json

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger()

__version__ = "0.0.1"

def resolve_link(url):
  if '/uresolver' in url:
    resolver_host = "csu-calpoly.userservices.exlibrisgroup.com"
    r = requests.get(url)
    tree = lxml.html.fromstring(r.text)
    sel = CSSSelector('ul>li')
    results = sel(tree)
    if results[0].text == 'No online access available':
      return 'NO RESULT'
    else:
      sel = CSSSelector('a')
      results = sel(tree)
      if len(results) > 0 and not results[0].get('href').startswith("http://lib.calpoly.edu") and not results[0].get('href').startswith("https://lib.calpoly.edu"):
        resolver_url = results[2].get('href')
        if resolver_url.startswith("http"):
          pass
        elif resolver_url.startswith("/"):
          resolver_url = "https://{}{}".format(resolver_host, resolver_url)
        else:
          return 'INVALID LINK TO RESOLVE: resolver_host: {} resolver_url: {}'.format(resolver_host, resolver_url)
        r = requests.get(resolver_url, allow_redirects=False)
        if 'Location' in r.headers:
          return r.headers['Location']
        else:
          return 'LINK DOES NOT RESOLVE'
      else:
        return "BAD LINK {}".format(url)
  else:
    return url

def may_be_ebook(doc):
  if ('delivery' in doc):
    if doc['pnx']['display']['type'][0] == 'book' or doc['pnx']['display']['type'][0] == 'book_chapter': 
      return (
        doc['delivery']['availability'][0] == 'fulltext' or
        doc['delivery']['availability'][0] == 'fulltext_linktorsrc' or
        doc['delivery']['availability'][0] == 'not_restricted' or
        'Alma-E' in doc['delivery']['deliveryCategory'] or
        'Remote Search Resource' in doc['delivery']['deliveryCategory']
      )
    else:
      return False
  else:
    return False

def get_last_link(url):
  session = requests.Session()
  last = False
  prefix = ''
  proxied_url = url
  url = url.replace('http://ezproxy.lib.calpoly.edu/login?url=', '')
  if url != proxied_url:
    prefix = 'http://ezproxy.lib.calpoly.edu/login?url='
  while url.startswith("http") and not last:
    parse_result = requests.utils.urlparse(url)
    previous_url_start = "{}://{}".format(parse_result.scheme, parse_result.netloc)
    # logger.info("previous_url_start: {}".format(previous_url_start)) 
    headers = { 'User-Agent': 'insomnia/6.6.2' }  
    r = session.get(url, headers=headers, allow_redirects=False)
    if 'Location' in r.headers:
      url = r.headers['Location']
    else:
      last = True
    if url.startswith('/'):
      url = "{}{}".format(previous_url_start, url)
  return "{}{}".format(prefix, url)

def canonicalize_link(url):
  if url:
    url = url.replace('onlinelibrary.wiley.com/doi/book/', 'onlinelibrary.wiley.com/book/')
    url = url.replace('http://ezproxy.lib.calpoly.edu/login?url=https://ebookcentral.proquest.com/', 'https://ebookcentral.proquest.com/')
  return url

def get_primo_match(isbn, titles_dict):
  results = []
  if isbn == "":
    results.append('NO ISBN')
  elif not isbn.isdigit():
    results.append('INVALID ISBN')
  else:
    primo_apikey = os.environ['PRIMO_API_KEY']
    limit = 30
    api_url = "https://api-na.hosted.exlibrisgroup.com/primo/v1/pnxs?q=isbn,contains,{}&offset=0&limit={}&view=full&inst=01CALS_PSU&scope=Everything&vid=01CALS_PSU:01CALS_PSU&apikey={}".format(isbn, limit, primo_apikey)
    # logger.info("api_url: {}".format(api_url))    
    data = requests.get(api_url).json()

    if 'errorMessage' in data:
      results.append(data['errorMessage'])
    elif 'docs' not in data or ('docs' in data and len(data['docs']) == 0):
      results.append('NO MATCH')
    else:
      match = False
      for doc in data['docs']:
        if (may_be_ebook(doc)):
          links_to_resolve = []
          if 'almaOpenurl' in doc['delivery']:
            links_to_resolve.append(doc['delivery']['almaOpenurl'])
          if 'link' in doc['delivery']:
            for item in doc['delivery']['link']:
              if 'linkURL' in item and 'linkType' in item and item['linkType'] == 'addlink':
                links_to_resolve.append(item['linkURL'])
          if 'display' in doc['pnx'] and 'mms' in doc['pnx']['display']:
            mms = doc['pnx']['display']['mms'][0]
            links_to_resolve.append("https://na03.alma.exlibrisgroup.com/view/uresolver/01CALS_PSU/openurl?rft.mms_id={}".format(mms))
          for link_to_resolve in links_to_resolve:
            if link_to_resolve is not None and '{{userIp}}' not in link_to_resolve:
              match = True
              # logger.info("link_to_resolve: {}".format(link_to_resolve))
              resolved_link = resolve_link(link_to_resolve)
              # logger.info("resolved_link: {}".format(resolved_link))
              if '/dx.doi.org/' in resolved_link:
                last_link = get_last_link(resolved_link)
                if last_link == resolved_link:
                  resolved_link = None
                else:
                  resolved_link = last_link              
              logger.info("resolved: {}".format(resolved_link))
              canonicalized_link = canonicalize_link(resolved_link)
              if not canonicalized_link in results and canonicalized_link is not None:
                title = doc['pnx']['display']['title'][0]
                if isbn in titles_dict:
                  if title not in titles_dict[isbn]:
                    titles_dict[isbn].append(title)
                else:
                  titles_dict[isbn] = [title]
                match = True
                results.append(canonicalized_link)
          else:
            if 'almaInstitutionsList' in doc['delivery'] and 'instCode' in doc['delivery']['almaInstitutionsList'] and doc['delivery']['almaInstitutionsList']['instCode'] == '01CALS_PSU':
              logger.info("EBOOK but no almaOpenurl")
              logger.info(json.dumps(doc['delivery']))
      if not match:
        if not 'NO MATCH' in results:
          results.append('NO MATCH')
  return results

def input_valid(input):
  return input.isdigit()

def output_results(input_filename, output_filename):
  titles_dict = {}
  matches_dict = {}
  with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ['Quarter','CourseNumber','Instructor','Author','Follett Title','Primo Title','Title','Edition','Publisher','ISBN', 'URL']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    with open(input_filename) as csvinfile:
      reader = csv.DictReader(csvinfile, delimiter=',')
      reader.fieldnames.append('URL')
      for row in reader:
        row['Follett Title'] = row['Title']
        isbn = row['ISBN']
        logger.info("{}".format(isbn))
        if isbn in matches_dict:
          matches = matches_dict[isbn]
        else:
          matches = get_primo_match(isbn, titles_dict)
          matches_dict[isbn] = matches
        if isbn in titles_dict:
          row['Primo Title'] = ';'.join(titles_dict[isbn])
          row['Title'] = row['Primo Title']
        else:
          row['Title'] = row['Follett Title']
        row['URL'] = ';'.join(matches)
        writer.writerow(row)

def main():
  if not 'PRIMO_API_KEY' in os.environ:
    print('PRIMO_API_KEY not set')
  elif len(sys.argv) == 2 and input_valid(sys.argv[1]):
    quarter = sys.argv[1]
    input_filename = "./textbooks_{}.csv".format(quarter)
    output_filename = "./textbooks_{}_results.csv".format(quarter)
    if os.path.isfile(output_filename):
      print("{} exists".format(output_filename))
    elif not os.path.isfile(input_filename):
      print("{} does not exist".format(input_filename))
    else:
      output_results(input_filename, output_filename)
  else:
    print('Usage:\n\tpython textbooks_match.py 117')

if __name__ == "__main__": main()

