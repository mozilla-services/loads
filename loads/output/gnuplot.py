from loads.util import temporary_file
import subprocess
import os


TEST_PERCENTAGE_TEMPLATE = """
set title "{title}"
set term png truecolor
set output "{output_filename}"
set key invert reverse Left outside
set key autotitle columnheader
set yrange [0:100]
set auto x
set ylabel "Tests ran (%)"
set xlabel "Concurrent users"

set style data histogram
set style histogram rowstacked
set style fill solid border -1
set boxwidth 0.2

plot '{data_file}' using 2:xtic(1) lc rgb"green" , "" using 3 lc rgb"red"
"""


TEST_REQUEST_TIME_TEMPLATE = """
set title "{title}"
set term png truecolor
set output "{output_filename}"
set key autotitle columnheader
set auto x
set xrange [0:{max_x}]
set yrange [{min_y}:{max_y}]
set ylabel "Request time"
set xlabel "Concurrent users"
set bars 4.0
set style fill empty

plot '{data_file}' using 1:3:2:4:4 with candlesticks notitle, \
     '' using 1:4:4:6:5 with candlesticks notitle, \
     '' using 1:4 lc rgb"green" with lines notitle

"""


class GNUPlotOutput(object):
    name = 'gnuplot'
    options = {'output-dir': ('A directory to output the GNUPlot-generated'
                              ' images to', str, '.', True)}

    def __init__(self, test_result, args):
        self.results = test_result
        self.args = args
        self.output_dir = args.get('output_gnuplot_output_dir')

    def flush(self):
        self.generate_test_percentages('ohyeah.png')
        self.generate_request_time('request-time.png')

    def generate_test_percentages(self, output_filename):
        data = [('Status', 'OK', 'KO')]
        for cycle in self.args['cycles']:
            success = self.results.test_success_rate(cycle=cycle) * 100
            errors = 100 - success
            data.append(map(str, (cycle, success, errors)))

        self.call_gnuplot(data, TEST_PERCENTAGE_TEMPLATE,
                          output_filename, title='oh yeah')

    def generate_request_time(self, output_filename):
        data = []
        for cycle in self.args['cycles']:
            quantiles = self.results.get_request_time_quantiles(cycle=cycle)
            data.append((cycle,) + quantiles)

        args = {'min_x': min([d[0] for d in data]) - 2,
                'min_y': min([d[1] - d[2] for d in data]),
                'max_x': max([d[0] for d in data]) + 2,
                'max_y': max([d[5] + d[2] for d in data])
        }

        data.insert(0, ('cycle', 'min', '%10', 'median', '%90', 'max'))

        self.call_gnuplot(data, TEST_REQUEST_TIME_TEMPLATE,
                          output_filename, title='oh yeah', args=args)

    def call_gnuplot(self, data, template, output_filename, title, args={}):
        with temporary_file() as (data_file, data_filename),\
             temporary_file() as (commands_file, commands_filename):
            data_file.writelines(['%s\n' % '\t'.join(map(str, l))
                                  for l in data])

            commands = template.format(
                    title=title,
                    output_filename=output_filename,
                    data_file=data_filename, **args)

            commands_file.write(commands)

        try:
            status = subprocess.call(['gnuplot',  commands_filename])
            if status != 0:
                raise Exception('Failed to run gnuplot, is it installed?')

        finally:
            for filename in (data_filename, commands_filename):
                os.remove(filename)

    def push(self, method_called, *args, **data):
        pass
