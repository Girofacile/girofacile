from datetime import date, time, datetime
from test_agents_feature import env


def test_usual_vehicle_uses_frequency_and_excludes_foreign_archived_and_cancelled_routes(env):
    from app.models import Driver, Vehicle, RoutePlan
    from app.routers.vehicles_drivers import driver_to_dict
    _, db, owner, other, *_ = env
    driver = Driver(user_id=owner.id, nome='Mario', cognome='Rossi')
    cars = [Vehicle(user_id=owner.id, nome='Abituale', targa='AA'), Vehicle(user_id=owner.id, nome='Recente', targa='BB'), Vehicle(user_id=other.id, nome='Altrui'), Vehicle(user_id=owner.id, nome='Archiviato', deleted_at=datetime.utcnow())]
    db.add_all([driver,*cars]);db.flush()
    def route(vehicle, day, status='completato', user_id=None):
        return RoutePlan(user_id=user_id or owner.id, driver_id=driver.id, vehicle_id=vehicle.id, nome='Test', data_giro=date(2026,1,day), orario_partenza=time(8), status=status)
    db.add_all([route(cars[0],1),route(cars[0],2),route(cars[1],3),route(cars[2],4),route(cars[3],5),route(cars[1],6,'annullato'),route(cars[1],7,user_id=other.id)]);db.commit()
    result=driver_to_dict(driver,db)
    assert result['mezzo_abituale']=={'id':cars[0].id,'nome':'Abituale','targa':'AA'}
    assert result['giri_assegnati']==6
    db.add(route(cars[1],8));db.commit()
    assert driver_to_dict(driver,db)['mezzo_abituale']['id']==cars[1].id
    db.query(RoutePlan).filter_by(driver_id=driver.id).delete();db.commit()
    assert driver_to_dict(driver,db)['mezzo_abituale'] is None
