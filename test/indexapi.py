#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2018, Silvio Peroni <essepuntato@gmail.com>
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
# SOFTWARE.

__author__ = 'essepuntato'
from urllib.parse import quote, unquote
from requests import get
from rdflib import Graph, URIRef
from re import sub
from json import loads
from datetime import datetime
from bs4 import BeautifulSoup
import re


def lower(s):
    return s.lower(),


def encode(s):
    return quote(s),


def decode_doi(res, *args):
    header = res[0]
    field_idx = []

    for field in args:
        field_idx.append(header.index(field))

    for row in res[1:]:
        for idx in field_idx:
            t, v = row[idx]
            row[idx] = t, unquote(v)

    return res, True


def merge(res, *args):
    final_result = []
    header = res[0]
    final_result.append(header)
    prefix_idx = header.index(args[0])
    citing_idx = header.index(args[1])
    cited_idx = header.index(args[2])

    citations = {}
    row_idx = 0
    for row in res[1:]:
        source = row[prefix_idx][1]
        citation = row[citing_idx][1], row[cited_idx][1]

        for idx in range(len(header)):
            t, v = row[idx]
            row[idx] = t, source.replace("/", " => ") + v
        if citation in citations:
            processed_row = citations[citation]
            for idx in range(len(header)):
                t, v = final_result[processed_row][idx]
                final_result[processed_row][idx] = t, v + "; " + row[idx][1]
        else:
            row_idx += 1
            citations[citation] = row_idx
            final_result.append(list(row))

    for row in final_result:
        row.pop(prefix_idx)

    return final_result, False


def split_dois(s):
    return "\"%s\"" % "\" \"".join(s.split("__")),

def split_pmids(s):
    return "\"%s\"" % "\" \"".join(s.split("__")),


def metadata(res, *args): #res è la tabella di sparql. la prende e inizia a fare delle operazioni. parte non dalla prima riga (intestazione) ma dalla riga successiva
    #recupera field secondo, perché la forma è sempre quella e so che è
    # doi, reference, citation_count
    header = res[0]
    doi_field = header.index("doi")
    additional_fields = ["author", "year", "title", "source_title", "volume", "issue", "page", "source_id"]

    header.extend(additional_fields)

    rows_to_remove = []

    for row in res[1:]:
        citing_doi = row[doi_field][1]

        r = None
        for p in (__crossref_parser, __datacite_parser):
            if r is None:
                r = p(citing_doi)

        if r is None or all([i in ("", None) for i in r]):
            rows_to_remove.append(row)
        else:
            row.extend(r)

    for row in rows_to_remove:
        res.remove(row)

    return res, True


def __get_issn(body):
    cur_id = ""
    if "ISSN" in body and len(body["ISSN"]):
        cur_id = "; ".join("issn:" + cur_issn for cur_issn in body["ISSN"])
    return __normalise(cur_id)


def __get_isbn(body):
    cur_id = ""
    if "ISBN" in body and len(body["ISBN"]):
        cur_id = "; ".join("isbn:" + cur_issn for cur_issn in body["ISBN"])
    return __normalise(cur_id)


def __get_id(body, f_list):
    cur_id = ""
    for f in f_list:
        if cur_id == "":
            cur_id = f(body)
    return __normalise(cur_id)


def __create_title_from_list(title_list):
    cur_title = ""

    for title in title_list:
        strip_title = title.strip()
        if strip_title != "":
            if cur_title == "":
                cur_title = strip_title
            else:
                cur_title += " - " + strip_title

    return __create_title(cur_title)


def __create_title(cur_title):
    return __normalise(cur_title.title())


def __normalise(o):
    if o is None:
        s = ""
    else:
        s = str(o)
    return sub("\s+", " ", s).strip()


def __crossref_parser(doi):
    api = "https://api.crossref.org/works/%s"

    try:
        r = get(api % doi,
                headers={"User-Agent": "COCI REST API (via OpenCitations - "
                                       "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
        if r.status_code == 200:
            json_res = loads(r.text)
            if "message" in json_res:
                body = json_res["message"]

                authors = []
                if "author" in body:
                    for author in body["author"]:
                        author_string = None
                        if "family" in author:
                            author_string = author["family"].title()
                            if "given" in author:
                                author_string += ", " + author["given"].title()
                                if "ORCID" in author:
                                    author_string += ", " + author["ORCID"].replace("http://orcid.org/", "")
                        if author_string is not None:
                            authors.append(__normalise(author_string))

                year = ""
                if "issued" in body and "date-parts" in body["issued"] and len(body["issued"]["date-parts"]) and \
                        len(body["issued"]["date-parts"][0]):
                    year = __normalise(body["issued"]["date-parts"][0][0])

                title = ""
                if "title" in body:
                    title = __create_title_from_list(body["title"])

                source_title = ""
                if "container-title" in body:
                    source_title = __create_title_from_list(body["container-title"])

                volume = ""
                if "volume" in body:
                    volume = __normalise(body["volume"])

                issue = ""
                if "issue" in body:
                    issue = __normalise(body["issue"])

                page = ""
                if "page" in body:
                    page = __normalise(body["page"])

                source_id = ""
                if "type" in body:
                    if body["type"] == "book-chapter":
                        source_id = __get_isbn(body)
                    else:
                        source_id = __get_issn(body)
                else:
                    source_id = __get_id(body, [__get_issn, __get_isbn])

                return ["; ".join(authors), year, title, source_title, volume, issue, page, source_id]

    except Exception as e:
        pass  # do nothing


def __datacite_parser(doi):
    api = "https://api.datacite.org/works/%s"

    try:
        r = get(api % doi,
                headers={"User-Agent": "COCI REST API (via OpenCitations - "
                                       "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
        if r.status_code == 200:
            json_res = loads(r.text)
            if "data" in json_res and "attributes" in json_res["data"]:
                body = json_res["data"]["attributes"]

                authors = []
                if "author" in body:
                    for author in body["author"]:
                        author_string = None
                        if "family" in author:
                            author_string = author["family"].title()
                            if "given" in author:
                                author_string += ", " + author["given"].title()
                                if "ORCID" in author:
                                    author_string += ", " + author["ORCID"].replace("http://orcid.org/", "")
                        if author_string is not None:
                            authors.append(__normalise(author_string))

                year = ""
                if "published" in body:
                    year = __normalise(body["published"])

                title = ""
                if "title" in body:
                    title = __create_title(body["title"])

                source_title = ""
                if "container-title" in body:
                    source_title = __create_title(body["container-title"])

                volume = ""
                issue = ""
                page = ""
                source_id = ""
                return ["; ".join(authors), year, title, source_title, volume, issue, page, source_id]

    except Exception as e:
        pass  # do nothing


def __nih_parser(pmid):
    api = "https://pubmed.ncbi.nlm.nih.gov/%s"
    pmid_sep = str(pmid) + "%s"
    display_opt = "/?format=pubmed"

    try:
        r = get(api % pmid_sep % display_opt,
                headers={"User-Agent": "NOCI REST API (via OpenCitations - "
                                       "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
        if r.status_code == 200:
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, features="lxml")
            body = str(soup.find(id="article-details"))

            authors = _get_author_nih(body)


            year = ""
            nih_date = _get_date_nih(body)
            if nih_date is not None:
                year = __normalise(nih_date)

            title = ""
            nih_title = _get_title_nih(body)
            if nih_title is not None:
                title = __create_title(nih_title)

            source_title = ""
            nih_cont_title = _get_cont_title_nih(body)
            if nih_cont_title is not None:
                source_title = __create_title(nih_cont_title)

            volume = ""
            issue = ""
            page = ""
            source_id = ""

            print (["; ".join(authors), year, title, source_title, volume, issue, page, source_id])
            return ["; ".join(authors), year, title, source_title, volume, issue, page, source_id]

    except Exception as e:
        pass  # do nothing

def _get_author_nih(txt_obj):
    result = []
    authors = re.findall("FAU\s+-\s+((([A-Z])\w*('|-|\.)?)(\s*([A-Z])\w*('|-|\.)?)*,\s*(([A-Z])([^\S\r\n][A-Z])*))", txt_obj)
    for i in authors:
        author = re.search("(([A-Z])\w*('|-|\.)?)(\s*([A-Z])\w*('|-|\.)?)*,\s*(([A-Z])([^\S\r\n][A-Z])*)", str(i)).group(0)
        result.append(__normalise(author))
    return result

def _get_title_nih(txt_obj):
    title = re.search("TI\s+-\s+([^\n]+)", txt_obj).group(1)
    re_search = re.search("([^\n]+)", title)
    if re_search is not None:
        result = re_search.group(0)
    return result

def _get_cont_title_nih(txt_obj):
    cont_title = re.search("JT\s+-\s+([^\n]+)", txt_obj).group(1)
    re_search = re.search("([^\n]+)", cont_title)
    if re_search is not None:
        result = re_search.group(0)
    return result


def _get_date_nih(txt_obj):
    date = re.search("DP\s+-\s+(\d{4}(\s?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))?(\s?((3[0-1])|([1-2][0-9])|([0]?[1-9])))?)", txt_obj).group(1)
    re_search = re.search("(\d{4})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+((3[0-1])|([1-2][0-9])|([0]?[1-9]))", date)
    if re_search is not None:
        result = re_search.group(0)
        datetime_object = datetime.strptime(result, '%Y %b %d')
        return datetime.strftime(datetime_object, '%Y-%m-%d')
    else:
        re_search = re.search("(\d{4})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", date)
        if re_search is not None:
            result = re_search.group(0)
            datetime_object = datetime.strptime(result, '%Y %b')
            return datetime.strftime(datetime_object, '%Y-%m')
        else:
            re_search = re.search("(\d{4})", date)
            if re_search is not None:
                result = re.search("(\d{4})", date).group(0)
                datetime_object = datetime.strptime(result, '%Y')
                return datetime.strftime(datetime_object, '%Y')
            else:
                return None



def oalink(res, *args):
    base_api_url = "https://api.unpaywall.org/v2/%s?email=contact@opencitations.net"

    # doi, reference, citation_count
    header = res[0]
    doi_field = header.index("doi")
    additional_fields = ["oa_link"]

    header.extend(additional_fields)

    for row in res[1:]:
        citing_doi = row[doi_field][1]

        try:
            r = get(base_api_url % citing_doi,
                    headers={"User-Agent": "COCI REST API (via OpenCitations - "
                                           "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
            if r.status_code == 200:
                res_json = loads(r.text)
                if "best_oa_location" in res_json and res_json["best_oa_location"] is not None and \
                        "url" in res_json["best_oa_location"]:
                    row.append(res_json["best_oa_location"]["url"])
                else:
                    row.append("")  # empty element
            else:
                row.append("")  # empty element
        except Exception as e:
            row.append("")  # empty element

    return res, True



def metadata_pmid(res, *args):
    # pmid, reference, citation_count
    header = res[0]
    pmid_field = header.index("doi")
    additional_fields = ["author", "year", "title", "source_title", "volume", "issue", "page", "source_id"]

    header.extend(additional_fields)

    rows_to_remove = []

    for row in res[1:]:
        citing_pmid = row[pmid_field][1]

        r = None
        for p in (__nih_parser):
            if r is None:
                r = p(citing_pmid)

        if r is None or all([i in ("", None) for i in r]):
            rows_to_remove.append(row)
        else:
            row.extend(r)

    for row in rows_to_remove:
        res.remove(row)

    return res, True



def oalinkpmid(res, *args):
    base_api_url = "https://api.unpaywall.org/v2/%s?email=contact@opencitations.net"

    # pmid, reference, citation_count
    header = res[0]
    pmid_field = header.index("doi") #?
    additional_fields = ["oa_link"]

    header.extend(additional_fields)

    for row in res[1:]:
        citing_pmid = row[pmid_field][1]

        try:
            r = get(base_api_url % citing_pmid,
                    headers={"User-Agent": "NOCI REST API (via OpenCitations - "
                                           "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
            if r.status_code == 200:
                res_json = loads(r.text)
                if "best_oa_location" in res_json and res_json["best_oa_location"] is not None and \
                        "url" in res_json["best_oa_location"]:
                    row.append(res_json["best_oa_location"]["url"])
                else:
                    row.append("")  # empty element
            else:
                row.append("")  # empty element
        except Exception as e:
            row.append("")  # empty element

    return res, True