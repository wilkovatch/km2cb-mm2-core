import sys
import csv
from utils import clean_city_path, create_folder_if_not_exists


class PropRulesExporter:
    def __init__(self, json_processor, verbose):
        self.json_processor = json_processor
        self.verbose = verbose

    def export_props_rules(self, filename):
        #get the unique elements
        elems = []
        for rules in self.json_processor.prop_rules:
            for rule in rules:
                for elem in rule['elements']:
                    if elem not in elems:
                        elems.append(elem)

        # get the new rules in the new format
        # (with indices instead of names since they could change names later)
        # (the name change cannot be done earlier otherwise the index function would not work)
        new_rules = []
        n = 0
        for rule in self.json_processor.prop_rules:
            n += 1
            new_rule = {}
            n_name = 'n' + str(n).zfill(2)
            new_rule['name'] = n_name
            left = rule[0]
            right = rule[1]
            new_left = {'name': n_name + 'left', 'elems': []}
            new_right = {'name': n_name + 'right', 'elems': []}
            if left is not None:
                for elem in left['elements']:
                    new_left['elems'].append(elems.index(elem))
            if right is not None:
                for elem in right['elements']:
                    new_right['elems'].append(elems.index(elem))
            new_rule['leftRule'] = new_left
            new_rule['rightRule'] = new_right
            new_rules.append(new_rule)

        # make names unique
        taken_names = []
        for elem in elems:
            if elem['name'] in taken_names:
                n = 2
                while (elem['name'] + str(n)) in taken_names:
                    n += 1
                elem['name'] += str(n)
            taken_names.append(elem['name'])

        # assign the modified elements
        for i in range(len(new_rules)):
            new_rule = new_rules[i]
            l_elems = new_rule['leftRule']['elems']
            r_elems = new_rule['rightRule']['elems']
            for j in range(len(r_elems)):
                r_elems[j] = elems[r_elems[j]]['name']
            for j in range(len(l_elems)):
                l_elems[j] = elems[l_elems[j]]['name']
            new_rule['leftRule']['elems'] = l_elems
            new_rule['rightRule']['elems'] = r_elems
            new_rules[i] = new_rule

        self.write_prop_rules(elems, new_rules, filename)

    def write_prop_rules(self, defs, rules, filename):
        def get_rule(r, num, side):
            if num > 99:
                print('too many rules, max is 99')
                sys.exit(1)
            strnum = ''
            if num < 10: strnum = '0' + str(num)
            else: strnum += str(num)
            realname = 'n' + strnum + side
            row = [realname]
            if r['elems'] is not None:
                for e in r['elems']:
                    row.append(e)
                if len(row) > 9:
                    print('too many elems in rule ' + r['name'] + ', max is 8')
                    sys.exit(1)
            return row

        def clean_row(row, pad):
            new_row = []
            for elem in row:
                if elem is str: new_row.append(elem.rstrip('\r\n'))
                else: new_row.append(elem)
            return new_row

        foldername = clean_city_path(filename) + '/'
        create_folder_if_not_exists(foldername)

        #rules
        f_rules = open(foldername + 'proprules.csv', 'w', newline='')
        writer = csv.writer(f_rules)
        header = ['rulename', 'prop1', 'prop2', 'prop3', 'prop4', 'prop5', 'prop6', 'prop7', 'prop8']
        writer.writerow(header)
        i=1
        for r in rules:
            writer.writerow(clean_row(get_rule(r['leftRule'], i, 'left'), len(header)))
            writer.writerow(clean_row(get_rule(r['rightRule'], i, 'right'), len(header)))
            i += 1
        f_rules.close()

        #defs
        f_defs = open(foldername + 'propdefs.csv', 'w', newline='')
        writer = csv.writer(f_defs)
        header = ['name', 'start', 'distance', 'maxUse', 'minLerp', 'maxLerp', 'file1', 'file2', 'file3', 'file4', '']
        writer.writerow(header)
        for d in defs:
            row = [d['name'], d['start'], d['elemDistance'], d['maxNumber'], d['minHorizPos'], d['maxHorizPos']]
            for mesh in d['meshes']:
                clean_mesh = mesh.replace('\\', '/').split('/')[-1].split('.')[0]
                row.append(clean_mesh)
            if len(row) > 11:
                print('too many meshes in elem ' + d['name'] + ', max is 5')
                sys.exit(1)
            writer.writerow(clean_row(row, len(header)))
        f_defs.close()
        print("Prop rules exported!")
