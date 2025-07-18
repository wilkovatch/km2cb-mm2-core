import shutil
from pathlib import Path
from utils import state_val, state_bool, state_vector, state_vector_scale, clean_city_path, create_folder_if_not_exists


class CinfoAimapExporter:
    def __init__(self, json_processor, verbose):
        self.json_processor = json_processor
        self.verbose = verbose
        self.filename = None
        self.bai_warning_printed = False
        self.bai_data = None

    def get_bai_data(self):
        pass

    def snap_to_bai(self, pos):
        # TODO: parse BAI and snap pos to nearest intersection (if within reasonable range)
        return pos

    def export_opponent(self, racesubfolder, opponent, opponent_id):
        model = state_val(opponent, "carModel", None)
        if model is None:
            return
        pos0 = state_vector(model, "localPosition")
        rot0 = state_vector(model, "localRotation")
        rot0_y = rot0["y"] if rot0["y"] != 0 else 0.001 # exactly 0 breaks things
        waypoints = state_val(opponent, "waypoints", [])
        lines = [
            "x,y,z,brake,forward offset,side offset,target speed,speed start,side start",
            ",".join([str(-pos0["x"]), str(pos0["y"]), str(pos0["z"]), str(rot0_y), "0", "0", "0", "0"]),
        ]
        for w in waypoints:
            wdata = state_val(w, "waypoint", None)
            if wdata is not None:
                pos = state_vector(wdata, "localPosition")
                pos = self.snap_to_bai(pos)
                line = ",".join([str(-pos["x"]), str(pos["y"]), str(pos["z"]), "0", "0", "0", "0", "0"])
                lines.append(line)
        oppfilename = racesubfolder + "/" + opponent_id + ".opp"
        oppfile = open(oppfilename, 'w', newline='')
        oppfile.writelines(line + '\n' for line in lines)
        oppfile.close()

    def get_opponent_str(self, car, opponent_id):
        model = state_val(car, "carModel", None)
        if model is None:
            return ""
        m = Path(state_val(model, "meshPath", "vpbug.pkg")).stem
        oppfilename = opponent_id + ".opp"
        speed_mult = str(state_val(car, "speedMultiplier", 1.0))
        caution = str(state_val(car, "cautionInCorners", 50.0))
        caution_t = str(state_val(car, "cautionInCornersThreshold", 0.7))
        avoid_traffic = str(int(state_bool(car, "avoidTraffic")))
        avoid_props = str(int(state_bool(car, "avoidProps")))
        avoid_players = str(int(state_bool(car, "avoidPlayers")))
        avoid_opponents = str(int(state_bool(car, "avoidOpponents")))
        bad_pathfinding = str(int(state_bool(car, "badPathfinding")))
        braking_bias = str(state_val(car, "brakingBias", 1.0))
        return " ".join([
            m, oppfilename, speed_mult, "0", caution, caution_t,
            avoid_traffic, avoid_props, avoid_players, avoid_opponents,
            bad_pathfinding, braking_bias
        ])

    def get_opponent_id(self, race_id, i, is_professional):
        return race_id + "-" + ("p" if is_professional else "a") + "-" + str(i)

    def get_race_array_in_container(self, data, key, is_p):
        container = state_val(data, key + ("_professional" if is_p else ""), [])
        array = state_val(container, key, [])
        if array == [] and is_p:
            container = state_val(data, key, [])
            array = state_val(container, key, [])
        return array

    def export_race_aimap_and_opponents(self, racesubfolder, race, race_id, is_professional):
        is_p = is_professional
        aimapfilename = racesubfolder + "/" + race_id + ".aimap" + ("_p" if is_p else "")
        aimap = open(aimapfilename, 'w', newline='')

        density = str(state_val(race, "trafficDensity", 0.0))

        speed_limit = str(state_val(race, "speedLimit", 0.0))

        police_cars = self.get_race_array_in_container(race, "policeCars", is_p)
        police_cars_str = "\n".join(self.get_police_car_str(car) for car in police_cars)

        opponents = self.get_race_array_in_container(race, "opponents", is_p)
        opponents_str = "\n".join(self.get_opponent_str(opponents[i], self.get_opponent_id(race_id, i, is_p)) for i in range(len(opponents)))

        lines = [
            "# Ambient Traffic Density",
            "[Density]",
            str(density),
            "",
            "# Default Road Speed Limit",
            "[Speed Limit]",
            str(speed_limit),
            "",
            "# Ambient Traffic Exceptions",
            "# Rd Id, Density, Speed Limit",
            "[Exceptions]",
            "0",
            "",
            "# Police Init",
            "# Geo File, StartLink, Start Dist, Start Mode, Start Lane, Patrol Route",
            "[Police]",
            str(len(police_cars)),
            police_cars_str,
            "",
            "# Opponent Init",
            "# Geo File, WavePoint File",
            "# vpfer vpbug vpcaddie vpmtruck",
            "[Opponent]",
            str(len(opponents)),
            opponents_str,
        ]
        aimap.writelines(line + '\n' for line in lines)
        aimap.close()
        for i in range(len(opponents)):
            self.export_opponent(racesubfolder, opponents[i], self.get_opponent_id(race_id, i, is_p))
        return aimapfilename

    def export_race(self, racesubfolder, race, race_id):
        # aimap
        aimapfilename = self.export_race_aimap_and_opponents(racesubfolder, race, race_id, False)

        # aimap_p
        opponents_a = self.get_race_array_in_container(race, "opponents", False)
        opponents_p = self.get_race_array_in_container(race, "opponents", True)
        if opponents_p is None:
            opponents_p = opponents_a
            shutil.copy(aimapfilename, aimapfilename + "_p")
        else:
            self.export_race_aimap_and_opponents(racesubfolder, race, race_id, True)

        # waypoints
        waypointsfilename = racesubfolder + "/" + race_id + "waypoints.csv"
        waypointsfile = open(waypointsfilename, 'w', newline='')
        lines = [
            "x,y,z,a,poly count,frane rate,state changes,texture changes,msg",
        ]
        checkpoints = state_val(race, "checkpoints", [])
        for c in checkpoints:
            cm = state_val(c, "checkpoint", {})
            pos = state_vector(cm, "localPosition")
            rot = state_vector(cm, "localRotation")
            scale = state_vector_scale(cm, "localScale")
            rot_y = rot["y"] if rot["y"] != 0 else 0.001 # exactly 0 triggers some kind of automatic rotation+position towards the next one
            lines.append(",".join([str(-pos["x"]), str(pos["y"]), str(pos["z"]),  str(rot_y), str(scale["x"]), "0", "0", "0"]))
        waypointsfile.writelines(line + '\n' for line in lines)
        waypointsfile.close()

        # data for mm<blitz/circuit/race>data.csv
        time_of_day_a = state_val(race, "timeOfDay", 0)
        time_of_day_p = state_val(race, "timeOfDay_professional", time_of_day_a)

        weather_a = state_val(race, "weather", 0)
        weather_p = state_val(race, "weather_professional", weather_a)

        num_laps_a = state_val(race, "laps", 0)
        num_laps_p = state_val(race, "laps", num_laps_a)

        time_limit_a = state_val(race, "timeLimit", 0)
        time_limit_p = state_val(race, "timeLimit", time_limit_a)

        traffic_density_a = state_val(race, "trafficDensity", 0)
        traffic_density_p = state_val(race, "trafficDensity", traffic_density_a)

        ped_density_a = state_val(race, "pedestriansDensity", 0)
        ped_density_p = state_val(race, "pedestriansDensity", ped_density_a)

        return ",".join([
            "none",                            # Description (unused?)
            "0",                               # CarType (always 0?)
            str(time_of_day_a),                # TimeOfDay
            str(weather_a),                    # Weather
            str(len(opponents_a)),             # Opponents
            "1",                               # Cops (always 1?)
            str(traffic_density_a),            # Ambient
            str(ped_density_a),                # Peds
            str(num_laps_a),                   # NumLaps
            str(time_limit_a),                 # TimeLimit
            "1",                               # Difficulty (always 1?)
            "0",                               # ProCarType (always 0?)
            str(time_of_day_p),                # ProTimeOfDay
            str(weather_p),                    # ProWeather
            str(len(opponents_p)),             # ProOpponents
            "1",                               # ProCops (always 1?)
            str(traffic_density_a),            # ProAmbient
            str(ped_density_p),                # ProPeds
            str(num_laps_p),                   # ProNumLaps
            str(time_limit_p),                 # ProTimeLimit
            "1",                               # ProDifficulty (always 1?)
        ])

    def get_police_car_str(self, car):
        model = state_val(car, "carModel", None)
        if model is None:
            return ""
        m = Path(state_val(model, "meshPath", "vpcop.pkg")).stem
        pos = state_vector(model, "localPosition")
        rot = state_vector(model, "localRotation")
        rot_y = rot["y"] if rot["y"] != 0 else 0.001 # exactly 0 breaks things
        transf = " ".join([str(-pos["x"]), str(pos["y"]), str(pos["z"]), str(rot_y)])
        return m + "\t" + transf + " 0 15 0.5 50.0"

    def export_roam_aimap(self, racesubfolder, data):
        aimapfilename = racesubfolder + "/roam.aimap"
        aimap = open(aimapfilename, 'w', newline='')

        speed_limit = str(state_val(data, "speedLimit", 0.0))

        drive_on_left = "1" if state_val(data, "driveOnLeft", False) else "0"

        police_cars_container = state_val(data, "roamPoliceCars", [])
        police_cars = state_val(police_cars_container, "policeCars", [])
        police_cars_str = "\n".join(self.get_police_car_str(car) for car in police_cars)

        lines = [
            "[AmbientLaneChanges]",
            "1",
            "",
            "[Exceptions]",
            "0",
            "",
            "# Police Init",
            "# Geo File, StartLink, Start Dist, Start Mode, Start Lane, Patrol Route",
            "[Police]",
            str(len(police_cars)),
            police_cars_str,
            "",
            "[Opponent]",
            "0",
            "",
            "[Hookmen]",
            "0",
        ]
        aimap.writelines(line + '\n' for line in lines)
        aimap.close()
        shutil.copy(aimapfilename, aimapfilename + "_p")

    def export_city_aimap(self, filename, data):
        aimapfilename = str(Path(filename).with_suffix('.aimap'))
        aimap = open(aimapfilename, 'w', newline='')
        speed_limit = str(state_val(data, "speedLimit", 0.0))
        drive_on_left = "1" if state_val(data, "driveOnLeft", False) else "0"

        #ambient cars
        ambient_cars = state_val(data, "trafficCars", [])
        traffic_total = sum(max(state_val(car, "frequency", 1), 1) for car in ambient_cars)
        for car in ambient_cars:
            car["adjFreq"] = max(state_val(car, "frequency", 1), 1) / traffic_total
        cur_range = 0
        for i in range(len(ambient_cars)):
            ambient_cars[i]["range"] = ambient_cars[i]["adjFreq"] + cur_range
            cur_range += ambient_cars[i]["adjFreq"]
        ambient_cars[-1]["range"] = 1 # the last must be 1, this is to avoid rounding issues
        ambient_cars_str = "\n".join(Path(car["carModel"]).stem + " " + str(car["range"]) + " 0" for car in ambient_cars)

        peds = state_val(data, "pedModels", [])
        peds_str = "\n".join(ped["goodWeatherPedName"] + " " + ped["badWeatherPedName"] for ped in peds)
        trafl1 = Path(state_val(data, "trafficLight1", "geometry/sp_traflitsingle_f.pkg")).stem
        trafl2 = Path(state_val(data, "trafficLight2", "geometry/sp_traflitdual_f.pkg")).stem
        traf_lights_str = trafl1 + " " + trafl2
        lines = [
            "[Speed Limit]",
            speed_limit,
            "",
            "[Ambients Drive On The Left]",
            drive_on_left,
            "",
            "[Ambient Types/Density]",
            str(len(ambient_cars)),
            ambient_cars_str,
            "",
            "[GoodWeatherPedName / BadWeatherPedName]",
            str(len(peds)),
            peds_str,
            "",
            "[Traffic Lights]",
            traf_lights_str
        ]
        aimap.writelines(line + '\n' for line in lines)
        aimap.close()

    def parse_race_names(self, races):
        return '|'.join(state_val(race, "name", "noname") for race in races)

    def export_races_csv(self, racesubfolder, races, racetype):
        header =("Description, CarType, TimeofDay, Weather, Opponents, Cops, "
                 "Ambient, Peds, NumLaps, TimeLimit, Difficulty, "
                 "ProCarType, ProTimeofDay, ProWeather, ProOpponents, ProCops, "
                 "ProAmbient, ProPeds, ProNumLaps, ProTimeLimit, ProDifficulty")
        lines = [header]
        lines.extend(races)
        csvfilename = racesubfolder + "/mm" + racetype + "data.csv"
        csvfile = open(csvfilename, 'w', newline='')
        csvfile.writelines(line + '\n' for line in lines)
        csvfile.close()

    def export_cinfo_aimap(self, filename):
        self.filename = filename
        if "cityProperties" not in self.json_processor.data:
            print("cityProperties not found, skipping cinfo and aimap")
            return
        p = self.json_processor.data['cityProperties']
        citypath = clean_city_path(filename)
        cityname = Path(filename).stem

        # parse the data
        localized_name = state_val(p, "cityName", "noname")
        blitz_races = state_val(p, "blitzRaces", [])
        circuit_races = state_val(p, "circuitRaces", [])
        checkpoint_races = state_val(p, "checkpointRaces", [])
        blitz_count = len(blitz_races)
        circuit_count = len(circuit_races)
        checkpoint_count = len(checkpoint_races)
        blitz_names = self.parse_race_names(blitz_races)
        circuit_names = self.parse_race_names(circuit_races)
        checkpoint_names = self.parse_race_names(checkpoint_races)

        # write the cinfo
        tunefolder = citypath + '_tune/'
        create_folder_if_not_exists(tunefolder)
        cinfo = open(tunefolder + cityname + '.cinfo', 'w', newline='')
        cinfo_lines = [
            "LocalizedName=" + localized_name,
            "MapName=" + cityname,
            "RaceDir=" + cityname,
            "BlitzCount=" + str(blitz_count),
            "CircuitCount=" + str(circuit_count),
            "CheckpointCount=" + str(checkpoint_count),
            "BlitzNames=" + blitz_names,
            "CircuitNames=" + circuit_names,
            "CheckpointNames=" + checkpoint_names,
            "MustPlace=1",
            "UnlockGroup=1",
        ]
        cinfo.writelines(line + '\n' for line in cinfo_lines)
        cinfo.close()

        # write the aimaps
        racefolder = citypath + '_race/'
        create_folder_if_not_exists(racefolder)
        racesubfolder = racefolder + cityname + '/'
        create_folder_if_not_exists(racesubfolder)

        self.export_city_aimap(filename, p)

        self.export_roam_aimap(racesubfolder, p)

        blitzdata = []
        for i in range(len(blitz_races)):
            race = blitz_races[i]
            blitzdata.append(self.export_race(racesubfolder, race, "blitz" + str(i)))
        self.export_races_csv(racesubfolder, blitzdata, "blitz")

        circuitdata = []
        for i in range(len(circuit_races)):
            race = circuit_races[i]
            circuitdata.append(self.export_race(racesubfolder, race, "circuit" + str(i)))
        self.export_races_csv(racesubfolder, circuitdata, "circuit")

        checkpointdata = []
        for i in range(len(checkpoint_races)):
            race = checkpoint_races[i]
            checkpointdata.append(self.export_race(racesubfolder, race, "race" + str(i)))
        self.export_races_csv(racesubfolder, checkpointdata, "race")

        print("cinfo and aimap exported!")
