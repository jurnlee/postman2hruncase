import io
import json
import logging
import os
import sys
import re
import argparse
import yaml

from compat import ensure_ascii

__version__ = '0.0.1'

class PostmanParser(object):
    def __init__(self, postman_testcase_file):
        self.postman_testcase_file = postman_testcase_file

    def read_postman_data(self):
        with open(self.postman_testcase_file, encoding='utf-8', mode='r') as file:
            postman_data = json.load(file)
        return postman_data
    
    def parse_url(self, request_url):
        url = ""
        if isinstance(request_url, str):
            url = request_url
        elif isinstance(request_url, dict):
            if "raw" in request_url.keys():
                url= request_url["raw"]
        return url
    
    def parse_header(self, request_header, apiVariables):
        headers = {}
        for header in request_header:
            headers[header["key"]] = self.parsePostmanVar(header["value"], apiVariables)
        return headers
    
    def parse_value_from_type(self, value):
        if isinstance(value, int):
            return int(value)
        elif isinstance(value, float):
            return float(value)
        elif str(value).lower() == "false":
            return False
        elif str(value).lower() == "true":
            return True
        else:
            return str(value)

    def parsePostmanVar(self, value, apiVariables):
        params = re.findall('\{\{([\w\W]+)}}', value)
        if params == []:
            return value
        for i in params:
            apiVariables.append({i:''})
        value = str(value).replace('{{', '$').replace('}}', '')
        return value

    def parse_each_item(self, item):
        """ parse each item in postman to testcase in httprunner
        """
        api = {}
        api["name"] = item["name"]
        api["validate"] = []
        api["variables"] = []

        request = {}
        request["method"] = item["request"]["method"]

        url = self.parse_url(item["request"]["url"])

        if request["method"] == "GET":
            request["url"] = self.parsePostmanVar(url.split("?")[0], api["variables"])
            request["headers"] = self.parse_header(item["request"]["header"], api["variables"])

            body = {}
            if "query" in item["request"]["url"].keys():
                for query in item["request"]["url"]["query"]:
                    api["variables"].append({query["key"]: self.parse_value_from_type(query["value"])})
                    body[query["key"]] = "$"+query["key"]
            request["params"] = body
        else:
            request["url"] = self.parsePostmanVar(url, api["variables"])
            request["headers"] = self.parse_header(item["request"]["header"], api["variables"])

            body = {}
            hasBody = 'body' in item["request"].keys()
            if hasBody and item["request"]["body"] != {}:
                mode = item["request"]["body"]["mode"]
                if isinstance(item["request"]["body"][mode], list):
                    for param in item["request"]["body"][mode]:
                        if param["type"] == "text":
                            api["variables"].append({param["key"]: self.parse_value_from_type(param["value"])})
                        else:
                            api["variables"].append({param["key"]: self.parse_value_from_type(param["src"])})
                        body[param["key"]] = "$"+param["key"]
                elif isinstance(item["request"]["body"][mode], str):
                    body = self.parsePostmanVar(item["request"]["body"][mode], api["variables"])
            request["data"] = body

        api["request"] = request
        return api
    
    def parse_items(self, items, folder_name=None):
        result = []
        for item in items:
            isFolder = 'item' in item.keys()
            if isFolder:
                name = item["name"].replace(" ", "_")
                if folder_name:
                    name = os.path.join(folder_name, name)
                temp = self.parse_items(item["item"], name)
                result += temp
            else:
                api = self.parse_each_item(item)
                api["folder_name"] = folder_name
                result.append(api)
        return result

    def parse_data(self):
        """ dump postman data to json testset
        """
        logging.info("Start to generate JSON testset.")
        postman_data = self.read_postman_data()

        result = self.parse_items(postman_data["item"], None)
        return result

    def save(self, data, output_dir, output_file_type="json"):
        count = 0
        output_dir = os.path.join(output_dir, "api")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        for each_api in data:
            count += 1
            file_name = str(count) + "." + output_file_type
            
            folder_name = each_api.pop("folder_name")
            if folder_name:
                folder_path = os.path.join(output_dir, folder_name)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)
                file_path = os.path.join(folder_path, file_name)
            else:
                file_path = os.path.join(output_dir, file_name)
            if os.path.isfile(file_path):
                logging.error("{} file had exist.".format(file_path))
                continue
            if output_file_type == "json":
                with io.open(file_path, 'w', encoding="utf-8") as outfile:
                    my_json_str = json.dumps(each_api, ensure_ascii=ensure_ascii, indent=4)
                    if isinstance(my_json_str, bytes):
                        my_json_str = my_json_str.decode("utf-8")
                    outfile.write(my_json_str)
            else:
                with io.open(file_path, 'w', encoding="utf-8") as outfile:
                    my_json_str = json.dumps(each_api, ensure_ascii=ensure_ascii, indent=4)
                    yaml.dump(each_api, outfile, allow_unicode=True, default_flow_style=False, indent=4)
                    
            logging.info("Generate JSON testset successfully: {}".format(file_path))



def main():
    parser = argparse.ArgumentParser(
        description="Convert postman testcases to JSON testcases for HttpRunner.")
    parser.add_argument("-V", "--version", dest='version', action='store_true', help="show version")
    parser.add_argument('--log-level', default='INFO',
        help="Specify logging level, default is INFO.")
    parser.add_argument('postman_testset_file', nargs='?',
        help="Specify postman testset file.")
    parser.add_argument('--output_file_type', default='json',
        help="Optional. Specify output file type.")
    parser.add_argument('--output_dir', default='.',
        help="Optional. Specify output directory.")

    args = parser.parse_args()
    if args.version:
        print("{}".format(__version__))
        exit(0)

    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(level=log_level)

    postman_testset_file = args.postman_testset_file
    output_file_type = args.output_file_type
    output_dir = args.output_dir

    if not postman_testset_file or not postman_testset_file.endswith(".json"):
        logging.error("postman_testset_file file not specified.")
        sys.exit(1)
    
    if not output_file_type:
        output_file_type = "json"
    else:
        output_file_type = output_file_type.lower()
    if output_file_type not in ["json", "yml", "yaml"]:
        logging.error("output file only support json/yml/yaml.")
        sys.exit(1)
    
    if not output_dir:
        output_dir = '.'

    postman_parser = PostmanParser(postman_testset_file)
    parse_result = postman_parser.parse_data()
    postman_parser.save(parse_result, output_dir, output_file_type=output_file_type)

    return 0

if __name__ == "__main__":
    main()
